# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Public holidays on an installation that was never set up, and holidays in and out as files.

The setup step has no button anywhere, so a live installation had no holiday
calendar at all: the Public holidays page had nothing to add a day to, and Add
did nothing without a word. These cover making the calendar on first use, the
same for the reasons for being away, and moving a calendar through a spreadsheet.
"""

# Python imports
import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from uuid import uuid4

# Third-party imports
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import (
    HrAbsenceType,
    HrContract,
    HrEmploymentProfile,
    HrHoliday,
    HrHolidayCalendar,
    HrImportBatch,
    HrWorkSchedule,
)
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

HEADERS = ["date", "name_de", "name_en", "half_day", "statutory"]


def new_user():
    return UserFactory(username=uuid4().hex)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def workspace():
    owner = new_user()
    workspace = WorkspaceFactory(owner=owner)
    WorkspaceMemberFactory(workspace=workspace, member=owner, role=ROLE.ADMIN.value)
    return workspace


def employ(workspace, is_hr_manager=False):
    user = new_user()
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.MEMBER.value)
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone="Europe/Vienna",
        hire_date=date(2024, 1, 1),
        is_hr_manager=is_hr_manager,
    )
    HrContract.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2024, 1, 1),
        arrangement=HrContract.Arrangement.ONSITE_FULL_TIME,
        records_target_hours=True,
    )
    return user


@pytest.fixture
def manager(workspace):
    return employ(workspace, is_hr_manager=True)


def calendar_for(workspace, **extra):
    return HrHolidayCalendar.objects.create(
        workspace=workspace, name="Österreich", country_code="AT", is_default=True, **extra
    )


def upload(rows, headers=HEADERS):
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return SimpleUploadedFile("holidays.csv", buffer.getvalue().encode("utf-8"), content_type="text/csv")


def check(client, rows, headers=HEADERS):
    return client.post(
        "/api/hr/imports/",
        {"file": upload(rows, headers), "kind": HrImportBatch.Kind.HOLIDAYS},
        format="multipart",
    )


class TestTheDefaultCalendarOnFirstUse:
    def test_it_is_made_and_filled_in_with_the_statutory_days(self, workspace, manager):
        response = client_for(manager).post("/api/hr/holiday-calendars/default/")

        assert response.status_code == 201
        body = response.json()
        assert body["created"] is True
        calendar = HrHolidayCalendar.objects.get()
        assert calendar.is_default and calendar.country_code == "AT"
        assert body["calendar"]["id"] == str(calendar.id)
        this_year = timezone.now().year
        assert HrHoliday.objects.filter(calendar=calendar, date=date(this_year, 11, 1)).exists()
        assert body["holidays_added"] == HrHoliday.objects.filter(calendar=calendar).count()

    def test_asking_again_changes_nothing(self, workspace, manager):
        client = client_for(manager)
        client.post("/api/hr/holiday-calendars/default/")
        removed = HrHoliday.objects.filter(date__month=1, date__day=6).first()
        removed.delete()
        count = HrHoliday.objects.count()

        response = client.post("/api/hr/holiday-calendars/default/")

        assert response.status_code == 200
        assert response.json()["created"] is False
        assert HrHolidayCalendar.objects.count() == 1
        # A day somebody removed by hand stays removed.
        assert HrHoliday.objects.count() == count

    def test_a_national_calendar_nobody_marked_as_default_becomes_it(self, workspace, manager):
        calendar = calendar_for(workspace)
        HrHolidayCalendar.objects.filter(pk=calendar.pk).update(is_default=False)

        response = client_for(manager).post("/api/hr/holiday-calendars/default/")

        assert response.status_code == 200
        assert HrHolidayCalendar.objects.count() == 1
        assert HrHolidayCalendar.objects.get().is_default

    def test_an_employee_cannot_make_it(self, workspace):
        response = client_for(employ(workspace)).post("/api/hr/holiday-calendars/default/")
        assert response.status_code == 403
        assert not HrHolidayCalendar.objects.exists()

    def test_it_does_not_touch_the_working_week(self, workspace, manager):
        client_for(manager).post("/api/hr/holiday-calendars/default/")
        assert not HrWorkSchedule.objects.filter(profile__isnull=True).exists()

    def test_a_day_can_be_added_once_it_exists(self, workspace, manager):
        client = client_for(manager)
        calendar_id = client.post("/api/hr/holiday-calendars/default/").json()["calendar"]["id"]

        # Not a day the seeding fills in: 24 and 31 December already are, as half days.
        response = client.post(
            "/api/hr/holidays/",
            {"calendar": calendar_id, "date": "2026-06-15", "name_de": "Betriebsurlaub", "is_statutory": False},
            format="json",
        )

        assert response.status_code == 201


class TestTheUsualReasonsOnFirstUse:
    def test_they_are_added_to_an_empty_list(self, workspace, manager):
        response = client_for(manager).post("/api/hr/absence-types/standard/")

        assert response.status_code == 201
        codes = {row["code"] for row in response.json()["absence_types"]}
        assert {"urlaub", "krankenstand", "zeitausgleich"} <= codes
        assert HrAbsenceType.objects.get(code="urlaub").consumes_leave_entitlement

    def test_a_list_somebody_started_is_left_alone(self, workspace, manager):
        HrAbsenceType.objects.create(workspace=workspace, code="ferien", name_de="Ferien")

        response = client_for(manager).post("/api/hr/absence-types/standard/")

        assert response.status_code == 200
        assert response.json()["created"] == 0
        assert list(HrAbsenceType.objects.values_list("code", flat=True)) == ["ferien"]

    def test_an_employee_cannot_add_them(self, workspace):
        response = client_for(employ(workspace)).post("/api/hr/absence-types/standard/")
        assert response.status_code == 403
        assert not HrAbsenceType.objects.exists()


class TestDownloadingTheCalendar:
    def test_a_year_comes_out_with_the_import_headings(self, workspace, manager):
        calendar = calendar_for(workspace)
        HrHoliday.objects.create(
            workspace=workspace, calendar=calendar, date=date(2026, 12, 24), name_de="Heiliger Abend",
            name_en="Christmas Eve", day_fraction=Decimal("0.5"), is_statutory=False,
        )
        HrHoliday.objects.create(
            workspace=workspace, calendar=calendar, date=date(2025, 12, 25), name_de="Christtag",
        )

        response = client_for(manager).get(f"/api/hr/holidays/export/?calendar={calendar.id}&year=2026")

        assert response.status_code == 200
        assert 'filename="holidays-osterreich-2026.csv"' in response["Content-Disposition"]
        rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))
        assert [cell.lower().replace(" ", "_") for cell in rows[0]] == HEADERS
        assert rows[1:] == [["2026-12-24", "Heiliger Abend", "Christmas Eve", "yes", "no"]]

    def test_without_a_calendar_named_the_default_is_used(self, workspace, manager):
        calendar = calendar_for(workspace)
        HrHoliday.objects.create(workspace=workspace, calendar=calendar, date=date(2026, 1, 1), name_de="Neujahr")

        response = client_for(manager).get("/api/hr/holidays/export/?file_format=xlsx")

        assert response.status_code == 200
        assert response["Content-Type"].startswith("application/vnd.openxmlformats")

    def test_an_employee_can_download_it(self, workspace):
        calendar_for(workspace)
        response = client_for(employ(workspace)).get("/api/hr/holidays/export/")
        assert response.status_code == 200

    def test_no_calendar_is_not_found(self, workspace, manager):
        response = client_for(manager).get("/api/hr/holidays/export/")
        assert response.status_code == 404


class TestImportingHolidays:
    def test_rows_are_checked_then_written_into_the_default_calendar(self, workspace, manager):
        calendar = calendar_for(workspace)
        client = client_for(manager)

        response = check(
            client,
            [
                {"date": "24.12.2026", "name_de": "Heiliger Abend", "name_en": "", "half_day": "ja", "statutory": "nein"},
                {"date": "2026-12-31", "name_de": "Silvester", "name_en": "New Year's Eve", "half_day": "yes", "statutory": ""},
            ],
        )

        assert response.status_code == 201
        batch = response.json()
        assert batch["valid_count"] == 2
        assert not HrHoliday.objects.exists()

        assert client.post(f"/api/hr/imports/{batch['id']}/commit/").status_code == 200
        eve = HrHoliday.objects.get(date=date(2026, 12, 24))
        assert eve.calendar_id == calendar.id
        assert eve.name_en == "Heiliger Abend"
        assert eve.day_fraction == Decimal("0.5")
        assert eve.is_statutory is False

    def test_a_day_already_in_the_calendar_is_left_as_it_is(self, workspace, manager):
        calendar = calendar_for(workspace)
        HrHoliday.objects.create(workspace=workspace, calendar=calendar, date=date(2026, 11, 1), name_de="Allerheiligen")

        batch = check(
            client_for(manager),
            [
                {"date": "2026-11-01", "name_de": "Something else", "name_en": "", "half_day": "", "statutory": ""},
                {"date": "2026-12-08", "name_de": "Mariä Empfängnis", "name_en": "", "half_day": "", "statutory": "yes"},
                {"date": "2026-12-08", "name_de": "Twice in the file", "name_en": "", "half_day": "", "statutory": ""},
            ],
        ).json()

        verdicts = [(row["verdict"], row.get("reason")) for row in batch["preview"]]
        assert verdicts == [("skip", "holiday_exists"), ("ok", ""), ("skip", "holiday_exists")]

    def test_unreadable_rows_say_why(self, workspace, manager):
        calendar_for(workspace)

        batch = check(
            client_for(manager),
            [
                {"date": "someday", "name_de": "X", "name_en": "", "half_day": "", "statutory": ""},
                {"date": "2026-05-01", "name_de": "", "name_en": "", "half_day": "", "statutory": ""},
                {"date": "2026-05-02", "name_de": "X", "name_en": "", "half_day": "maybe", "statutory": ""},
                {"date": "2026-05-03", "name_de": "X" * 121, "name_en": "", "half_day": "", "statutory": ""},
            ],
        ).json()

        reasons = [row["reason"] for row in batch["preview"]]
        assert reasons == ["bad_date", "name_missing", "bad_flag", "name_too_long"]
        assert batch["preview"][2]["detail"] == {"column": "half_day"}

    def test_without_a_calendar_every_row_says_so(self, workspace, manager):
        batch = check(
            client_for(manager),
            [{"date": "2026-05-01", "name_de": "Staatsfeiertag", "name_en": "", "half_day": "", "statutory": ""}],
        ).json()
        assert batch["preview"][0]["reason"] == "no_calendar"

    def test_a_calendar_column_picks_the_calendar(self, workspace, manager):
        calendar_for(workspace)
        germany = HrHolidayCalendar.objects.create(workspace=workspace, name="Deutschland", country_code="DE")

        batch = check(
            client_for(manager),
            [
                {"date": "2026-10-03", "name_de": "Tag der Deutschen Einheit", "calendar": "de"},
                {"date": "2026-10-04", "name_de": "X", "calendar": "Narnia"},
            ],
            headers=["date", "name_de", "calendar"],
        ).json()

        assert batch["preview"][0]["data"]["calendar_id"] == str(germany.id)
        assert batch["preview"][1]["reason"] == "unknown_calendar"
        assert batch["preview"][1]["detail"] == {"calendar": "Narnia"}

    def test_a_downloaded_calendar_comes_back_in_unchanged(self, workspace, manager):
        calendar = calendar_for(workspace)
        HrHoliday.objects.create(
            workspace=workspace, calendar=calendar, date=date(2026, 12, 31), name_de="Silvester",
            name_en="New Year's Eve", day_fraction=Decimal("0.5"), is_statutory=False,
        )
        client = client_for(manager)
        exported = client.get("/api/hr/holidays/export/?year=2026").content
        HrHoliday.objects.all().delete()

        batch_id = client.post(
            "/api/hr/imports/",
            {
                "file": SimpleUploadedFile("holidays.csv", exported, content_type="text/csv"),
                "kind": HrImportBatch.Kind.HOLIDAYS,
            },
            format="multipart",
        ).json()["id"]
        client.post(f"/api/hr/imports/{batch_id}/commit/")

        day = HrHoliday.objects.get()
        assert (day.date, day.name_de, day.name_en, day.day_fraction, day.is_statutory) == (
            date(2026, 12, 31),
            "Silvester",
            "New Year's Eve",
            Decimal("0.5"),
            False,
        )

    def test_undoing_takes_back_only_the_imported_days(self, workspace, manager):
        calendar = calendar_for(workspace)
        HrHoliday.objects.create(workspace=workspace, calendar=calendar, date=date(2026, 1, 1), name_de="Neujahr")
        client = client_for(manager)
        batch_id = check(
            client, [{"date": "2026-12-24", "name_de": "Heiliger Abend", "name_en": "", "half_day": "yes", "statutory": "no"}]
        ).json()["id"]
        client.post(f"/api/hr/imports/{batch_id}/commit/")

        response = client.post(f"/api/hr/imports/{batch_id}/undo/", {"reason": "Wrong year."}, format="json")

        assert response.status_code == 200
        assert response.json()["removed"] == 1
        assert list(HrHoliday.objects.values_list("name_de", flat=True)) == ["Neujahr"]

    def test_an_employee_cannot_import(self, workspace):
        calendar_for(workspace)
        response = check(
            client_for(employ(workspace)),
            [{"date": "2026-05-01", "name_de": "Staatsfeiertag", "name_en": "", "half_day": "", "statutory": ""}],
        )
        assert response.status_code == 403
