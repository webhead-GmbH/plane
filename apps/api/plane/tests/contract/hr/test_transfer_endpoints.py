# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Bringing old data in, and getting finished months out."""

# Python imports
import csv
from datetime import date
from io import StringIO
from uuid import uuid4

# Third-party imports
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import IssueWorkLog
from plane.hr.models import (
    HrContract,
    HrEmploymentProfile,
    HrImportBatch,
    HrOpeningBalance,
    HrPeriod,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.hr.services.ledger import rebuild_period
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

FULL = 462


def new_user(email=None):
    kwargs = {"username": uuid4().hex}
    if email:
        kwargs["email"] = email
    return UserFactory(**kwargs)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def url(workspace, path):
    return f"/api/hr/{path}"


def csv_upload(rows, headers, name="import.csv"):
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return SimpleUploadedFile(name, buffer.getvalue().encode("utf-8"), content_type="text/csv")


@pytest.fixture
def workspace():
    owner = new_user()
    workspace = WorkspaceFactory(owner=owner)
    WorkspaceMemberFactory(workspace=workspace, member=owner, role=ROLE.ADMIN.value)
    return workspace


def employ(workspace, email=None, is_hr_manager=False):
    user = new_user(email=email)
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
    HrWorkSchedule.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2024, 1, 1),
        monday_minutes=FULL,
        tuesday_minutes=FULL,
        wednesday_minutes=FULL,
        thursday_minutes=FULL,
        friday_minutes=FULL,
    )
    return user, profile


@pytest.fixture
def manager(workspace):
    user, _ = employ(workspace, email="hr@example.invalid", is_hr_manager=True)
    return user


class TestImportingHours:
    HEADERS = ["email", "date", "minutes", "note"]

    def test_a_file_is_checked_before_anything_is_written(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        upload = csv_upload(
            [{"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "480", "note": "March"}],
            self.HEADERS,
        )
        response = client_for(manager).post(
            url(workspace, "imports/"),
            {"file": upload, "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["row_count"] == 1
        assert body["valid_count"] == 1
        assert body["error_count"] == 0
        # Checked, not applied.
        assert not HrTimeEntry.objects.filter(profile=profile).exists()

    def test_committing_writes_the_rows_that_passed(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        upload = csv_upload(
            [
                {"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "480", "note": ""},
                {"email": "nobody@example.invalid", "date": "2026-03-02", "minutes": "60", "note": ""},
            ],
            self.HEADERS,
        )
        client = client_for(manager)
        batch_id = client.post(
            url(workspace, "imports/"),
            {"file": upload, "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        ).json()["id"]

        response = client.post(url(workspace, f"imports/{batch_id}/commit/"))
        assert response.status_code == 200
        assert response.json()["written"] == 1
        assert HrTimeEntry.objects.filter(profile=profile).count() == 1
        entry = HrTimeEntry.objects.get(profile=profile)
        assert entry.minutes == 480
        assert entry.source == HrTimeEntry.Source.IMPORT

    def test_an_import_never_creates_a_work_item_timer(self, workspace, manager):
        # The whole reason imported hours live in their own table. A timer is
        # mirrored to customer billing the moment it is saved, so importing three
        # years of history as timers would replay all of it into invoicing.
        employ(workspace, email="ana@example.invalid")
        before = IssueWorkLog.objects.count()
        upload = csv_upload(
            [
                {"email": "ana@example.invalid", "date": f"2026-03-{day:02d}", "minutes": "480", "note": ""}
                for day in range(2, 7)
            ],
            self.HEADERS,
        )
        client = client_for(manager)
        batch_id = client.post(
            url(workspace, "imports/"),
            {"file": upload, "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        ).json()["id"]
        client.post(url(workspace, f"imports/{batch_id}/commit/"))

        assert HrTimeEntry.objects.count() == 5
        assert IssueWorkLog.objects.count() == before

    def test_an_unreadable_row_says_which_one_and_why(self, workspace, manager):
        employ(workspace, email="ana@example.invalid")
        upload = csv_upload(
            [
                {"email": "ana@example.invalid", "date": "not-a-date", "minutes": "480", "note": ""},
                {"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "2000", "note": ""},
            ],
            self.HEADERS,
        )
        body = client_for(manager).post(
            url(workspace, "imports/"),
            {"file": upload, "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        ).json()
        assert body["error_count"] == 2
        messages = [row["message"] for row in body["preview"]]
        assert any("date" in message for message in messages)
        assert any("more than a day" in message.lower() for message in messages)
        # Row numbers count from the file, header included, so they match what
        # somebody sees in their spreadsheet.
        assert [row["row"] for row in body["preview"]] == [2, 3]

    def test_hours_for_a_closed_month_are_skipped_not_written(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        HrPeriod.objects.create(
            workspace=workspace,
            profile=profile,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            state=HrPeriod.State.LOCKED,
            target_minutes=0,
            actual_minutes=0,
            balance_minutes=0,
        )
        upload = csv_upload(
            [{"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "480", "note": ""}],
            self.HEADERS,
        )
        body = client_for(manager).post(
            url(workspace, "imports/"),
            {"file": upload, "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        ).json()
        assert body["valid_count"] == 0
        assert body["skipped_count"] == 1

    def test_hours_written_by_an_import_reach_the_month(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        upload = csv_upload(
            [{"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "480", "note": ""}],
            self.HEADERS,
        )
        client = client_for(manager)
        batch_id = client.post(
            url(workspace, "imports/"),
            {"file": upload, "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        ).json()["id"]
        client.post(url(workspace, f"imports/{batch_id}/commit/"))

        rebuild_period(profile, 2026, 3)
        from plane.hr.models import HrPeriodDay

        day = HrPeriodDay.objects.get(profile=profile, work_date=date(2026, 3, 2))
        assert day.non_project_minutes == 480

    def test_the_same_file_cannot_be_applied_twice(self, workspace, manager):
        employ(workspace, email="ana@example.invalid")
        rows = [{"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "480", "note": ""}]
        client = client_for(manager)

        first = client.post(
            url(workspace, "imports/"),
            {"file": csv_upload(rows, self.HEADERS), "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        ).json()
        client.post(url(workspace, f"imports/{first['id']}/commit/"))

        second = client.post(
            url(workspace, "imports/"),
            {"file": csv_upload(rows, self.HEADERS), "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        )
        assert second.status_code == 409
        assert HrTimeEntry.objects.count() == 1

    def test_an_employee_cannot_import(self, workspace):
        user, _ = employ(workspace, email="ana@example.invalid")
        upload = csv_upload(
            [{"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "60", "note": ""}],
            self.HEADERS,
        )
        response = client_for(user).post(
            url(workspace, "imports/"), {"file": upload}, format="multipart"
        )
        assert response.status_code == 403

    def test_a_file_that_is_not_a_spreadsheet_is_a_bad_request_not_a_crash(self, workspace, manager):
        upload = SimpleUploadedFile("notes.xlsx", b"this is not a spreadsheet", content_type="text/plain")
        response = client_for(manager).post(
            url(workspace, "imports/"),
            {"file": upload, "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        )
        assert response.status_code == 400


class TestUndoingAnImport:
    HEADERS = ["email", "date", "minutes", "note"]

    def _import(self, workspace, manager, rows):
        client = client_for(manager)
        batch_id = client.post(
            url(workspace, "imports/"),
            {"file": csv_upload(rows, self.HEADERS), "kind": HrImportBatch.Kind.TIME_ENTRIES},
            format="multipart",
        ).json()["id"]
        client.post(url(workspace, f"imports/{batch_id}/commit/"))
        return client, batch_id

    def test_undoing_removes_exactly_what_it_wrote(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        HrTimeEntry.objects.create(
            workspace=workspace, profile=profile, entry_date=date(2026, 2, 2), minutes=99
        )
        client, batch_id = self._import(
            workspace,
            manager,
            [{"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "480", "note": ""}],
        )
        assert HrTimeEntry.objects.count() == 2

        response = client.post(
            url(workspace, f"imports/{batch_id}/undo/"),
            {"reason": "Wrong file."},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["removed"] == 1
        # The entry that was there before is untouched.
        assert HrTimeEntry.objects.count() == 1
        assert HrTimeEntry.objects.get().minutes == 99

    def test_undoing_requires_a_reason(self, workspace, manager):
        employ(workspace, email="ana@example.invalid")
        client, batch_id = self._import(
            workspace,
            manager,
            [{"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "480", "note": ""}],
        )
        response = client.post(url(workspace, f"imports/{batch_id}/undo/"), {}, format="json")
        assert response.status_code == 409

    def test_hours_already_counted_into_a_closed_month_cannot_be_undone(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        client, batch_id = self._import(
            workspace,
            manager,
            [{"email": "ana@example.invalid", "date": "2026-03-02", "minutes": "480", "note": ""}],
        )
        period = HrPeriod.objects.create(
            workspace=workspace,
            profile=profile,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            state=HrPeriod.State.LOCKED,
            target_minutes=0,
            actual_minutes=0,
            balance_minutes=0,
        )
        HrTimeEntry.objects.filter(profile=profile).update(locked_period=period)

        response = client.post(
            url(workspace, f"imports/{batch_id}/undo/"),
            {"reason": "Changed our minds."},
            format="json",
        )
        assert response.status_code == 409
        assert HrTimeEntry.objects.count() == 1


class TestImportingOpeningBalances:
    HEADERS = ["email", "effective_on", "minutes", "kind", "basis", "confidence"]

    def test_a_balance_with_no_stated_basis_is_refused(self, workspace, manager):
        # A figure nobody can account for is one nobody can defend when the person
        # it belongs to disagrees with it.
        employ(workspace, email="ana@example.invalid")
        upload = csv_upload(
            [
                {
                    "email": "ana@example.invalid",
                    "effective_on": "2026-01-01",
                    "minutes": "600",
                    "kind": "time",
                    "basis": "",
                    "confidence": "agreed",
                }
            ],
            self.HEADERS,
        )
        body = client_for(manager).post(
            url(workspace, "imports/"),
            {"file": upload, "kind": HrImportBatch.Kind.OPENING_BALANCES},
            format="multipart",
        ).json()
        assert body["error_count"] == 1
        assert "based on" in body["preview"][0]["message"]

    def test_balances_are_written_with_how_sure_anybody_is(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        upload = csv_upload(
            [
                {
                    "email": "ana@example.invalid",
                    "effective_on": "2026-01-01",
                    "minutes": "10:30",
                    "kind": "time",
                    "basis": "Agreed with Ana at cut-over.",
                    "confidence": "agreed",
                }
            ],
            self.HEADERS,
        )
        client = client_for(manager)
        batch_id = client.post(
            url(workspace, "imports/"),
            {"file": upload, "kind": HrImportBatch.Kind.OPENING_BALANCES},
            format="multipart",
        ).json()["id"]
        client.post(url(workspace, f"imports/{batch_id}/commit/"))

        balance = HrOpeningBalance.objects.get(profile=profile)
        # "10:30" is ten and a half hours, not ten point three.
        assert balance.minutes == 630
        assert balance.confidence == HrOpeningBalance.Confidence.AGREED
        assert balance.basis.startswith("Agreed with Ana")


class TestOpeningBalanceCorrections:
    def test_correcting_a_balance_supersedes_rather_than_edits(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        client = client_for(manager)
        created = client.post(
            url(workspace, f"employees/{profile.id}/opening-balances/"),
            {
                "effective_on": "2026-01-01",
                "minutes": 600,
                "kind": HrOpeningBalance.Kind.TIME_BALANCE,
                "basis": "First pass.",
            },
            format="json",
        )
        assert created.status_code == 201
        original_id = created.json()["id"]

        corrected = client.patch(
            url(workspace, f"employees/{profile.id}/opening-balances/{original_id}/"),
            {"minutes": 720, "basis": "Ana disagreed; her figure accepted."},
            format="json",
        )
        assert corrected.status_code == 200

        original = HrOpeningBalance.objects.get(pk=original_id)
        assert original.minutes == 600
        assert original.superseded_by_id is not None
        assert original.superseded_by.minutes == 720

    def test_a_balance_needs_a_basis(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        response = client_for(manager).post(
            url(workspace, f"employees/{profile.id}/opening-balances/"),
            {"effective_on": "2026-01-01", "minutes": 600},
            format="json",
        )
        assert response.status_code == 400


class TestExport:
    def test_a_month_comes_out_with_the_columns_in_a_fixed_order(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        rebuild_period(profile, 2026, 3)
        response = client_for(manager).get(url(workspace, "export/?year=2026&month=3"))
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert "hr-2026-03.csv" in response["Content-Disposition"]

        rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
        # Whatever reads this expects the columns where it was told they would be,
        # so these keep their positions. Something appended after them is another
        # matter: a reader taking the columns it knows by index is unaffected, and
        # requiring exact equality would mean no column could ever be added.
        assert rows[0][:18] == [
            "Employee",
            "Email",
            "Period Start",
            "Period End",
            "State",
            "Target Minutes",
            "Target Hours",
            "Actual Minutes",
            "Actual Hours",
            "Balance Minutes",
            "Balance Hours",
            "Project Minutes",
            "Non Project Minutes",
            "Absence Minutes",
            "Holiday Minutes",
            "Leave Consumed Minutes",
            "Opening Balance Minutes",
            "Closing Balance Minutes",
        ]

    def test_a_month_still_running_says_how_far_the_figures_reach(self, workspace, manager):
        # The balance column owes the whole month while only part of it has been
        # worked, so on its own it reads as a shortfall for days nobody has
        # reached. These say how much of the month is actually in the figures.
        _, profile = employ(workspace, email="bea@example.invalid")
        rebuild_period(profile, 2026, 3)
        response = client_for(manager).get(url(workspace, "export/?year=2026&month=3"))

        rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
        assert rows[0][18:] == [
            "Counted Through",
            "Balance Minutes To Date",
            "Balance Hours To Date",
        ]
        # March 2026 is over, so the two balances agree.
        assert rows[1][18] == "2026-03-31"
        assert rows[1][19] == rows[1][9]

    def test_hours_go_out_as_both_minutes_and_decimal_hours(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        HrTimeEntry.objects.create(
            workspace=workspace, profile=profile, entry_date=date(2026, 3, 2), minutes=90
        )
        rebuild_period(profile, 2026, 3)
        response = client_for(manager).get(url(workspace, "export/?year=2026&month=3"))
        row = list(csv.DictReader(StringIO(response.content.decode("utf-8"))))[0]
        # Payroll works in decimal hours, but a disputed quarter of an hour needs
        # the exact figure to be there as well.
        assert row["Actual Minutes"] == "90"
        assert row["Actual Hours"] == "1.5"

    def test_xlsx_is_offered_too(self, workspace, manager):
        _, profile = employ(workspace, email="ana@example.invalid")
        rebuild_period(profile, 2026, 3)
        response = client_for(manager).get(url(workspace, "export/?year=2026&month=3&file_format=xlsx"))
        assert response.status_code == 200
        assert "spreadsheetml" in response["Content-Type"]
        assert response.content[:2] == b"PK"  # a zip, which is what xlsx is

    def test_a_person_can_export_their_own_month_day_by_day(self, workspace):
        user, profile = employ(workspace, email="ana@example.invalid")
        rebuild_period(profile, 2026, 3)
        period = HrPeriod.objects.get(profile=profile)
        response = client_for(user).get(url(workspace, f"periods/{period.id}/export/"))
        assert response.status_code == 200
        rows = list(csv.DictReader(StringIO(response.content.decode("utf-8"))))
        assert len(rows) == 31

    def test_a_person_can_have_their_month_as_a_spreadsheet_too(self, workspace):
        """The detail behind one payroll line, in the shape a spreadsheet opens.

        The whole-month export offers both shapes and so does the button on the
        person's own month, so the per-person route has to answer to xlsx as well
        — and it reads the format from ``file_format`` rather than ``format``,
        which the framework reserves for choosing its own renderer.
        """
        user, profile = employ(workspace, email="ana@example.invalid")
        rebuild_period(profile, 2026, 3)
        period = HrPeriod.objects.get(profile=profile)
        response = client_for(user).get(url(workspace, f"periods/{period.id}/export/?file_format=xlsx"))
        assert response.status_code == 200
        assert "spreadsheetml" in response["Content-Type"]
        assert response.content[:2] == b"PK"

    def test_one_person_cannot_export_anothers_month(self, workspace):
        user, _ = employ(workspace, email="ana@example.invalid")
        _, colleague = employ(workspace, email="bea@example.invalid")
        rebuild_period(colleague, 2026, 3)
        period = HrPeriod.objects.get(profile=colleague)
        response = client_for(user).get(url(workspace, f"periods/{period.id}/export/"))
        assert response.status_code == 404

    def test_an_employee_cannot_export_the_whole_month(self, workspace):
        user, _ = employ(workspace, email="ana@example.invalid")
        response = client_for(user).get(url(workspace, "export/?year=2026&month=3"))
        assert response.status_code == 403

    def test_a_month_that_was_not_asked_for_properly_is_a_bad_request(self, workspace, manager):
        response = client_for(manager).get(url(workspace, "export/?year=abc"))
        assert response.status_code == 400


class TestAgreeingAnOpeningBalance:
    """Who may say a starting figure is right.

    The worth of an agreed balance is that the person it belongs to agreed it.
    A manager able to tick that box on somebody's behalf would be recording
    their own opinion twice and calling the second one agreement.
    """

    def _balance(self, workspace, profile, minutes=-600, on=date(2026, 1, 1)):
        return HrOpeningBalance.objects.create(
            workspace=workspace,
            profile=profile,
            effective_on=on,
            kind=HrOpeningBalance.Kind.TIME_BALANCE,
            minutes=minutes,
            basis="Carried over from the spreadsheet.",
        )

    def test_the_person_can_agree_their_own(self, workspace):
        user, profile = employ(workspace)
        row = self._balance(workspace, profile)

        response = client_for(user).post(
            url(workspace, f"employees/{profile.id}/opening-balances/{row.id}/agree/")
        )
        assert response.status_code == 200
        row.refresh_from_db()
        assert row.acknowledged_at is not None
        assert row.acknowledged_by_id == user.id

    def test_a_manager_cannot_agree_it_for_them(self, workspace, manager):
        _, profile = employ(workspace)
        row = self._balance(workspace, profile)

        response = client_for(manager).post(
            url(workspace, f"employees/{profile.id}/opening-balances/{row.id}/agree/")
        )
        assert response.status_code == 403
        row.refresh_from_db()
        assert row.acknowledged_at is None

    def test_agreeing_twice_changes_nothing(self, workspace):
        user, profile = employ(workspace)
        row = self._balance(workspace, profile)
        path = url(workspace, f"employees/{profile.id}/opening-balances/{row.id}/agree/")

        client_for(user).post(path)
        row.refresh_from_db()
        first = row.acknowledged_at

        second = client_for(user).post(path)
        assert second.status_code == 200
        assert second.json()["already_agreed"] is True
        row.refresh_from_db()
        assert row.acknowledged_at == first

    def test_a_figure_already_replaced_cannot_be_agreed(self, workspace):
        # Agreeing a superseded number records assent to something nobody uses.
        user, profile = employ(workspace)
        old = self._balance(workspace, profile)
        # Only one figure per person, kind and date may be current, so a
        # correction carries its own date rather than sitting on top of the one
        # it replaces.
        replacement = self._balance(workspace, profile, minutes=-540, on=date(2026, 2, 1))
        old.superseded_by = replacement
        old.save()

        response = client_for(user).post(
            url(workspace, f"employees/{profile.id}/opening-balances/{old.id}/agree/")
        )
        assert response.status_code == 409

    def test_somebody_else_cannot_agree_it(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        row = self._balance(workspace, colleague)

        response = client_for(user).post(
            url(workspace, f"employees/{colleague.id}/opening-balances/{row.id}/agree/")
        )
        assert response.status_code in (403, 404)
        row.refresh_from_db()
        assert row.acknowledged_at is None

    def test_an_unagreed_balance_is_still_counted(self, workspace):
        # Refusing to count it would show a zero, which is a different wrong
        # number rather than a safe one. It is shown as unagreed instead.
        from plane.hr.services.closing import opening_balance_for
        from plane.hr.services.ledger import rebuild_period

        _, profile = employ(workspace)
        self._balance(workspace, profile, minutes=-600)
        period = rebuild_period(profile, 2026, 3)
        assert opening_balance_for(period) == -600
