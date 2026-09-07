# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Nothing new goes into a month that has stopped being rebuilt.

The marker each record carries — the month that locked it — is stamped at the
moment of closing, so it answers one question only: was this row counted into a
month that has since closed. A row written *afterwards* carries no marker at all,
and every check that reads one lets it straight through.

So until this was guarded, the closed month refused every edit and accepted every
addition. Somebody could add a day of leave, an attendance day, or four hours of
non-project time into a month already sent to payroll, and the figures — frozen,
never to be recomputed — would never mention it. The record and the payslip would
disagree, and the record would look like the authority.

Handed in and approved are the same case. Neither stamps a marker, and neither is
rebuilt again.
"""

# Python imports
from calendar import monthrange
from datetime import date
from uuid import uuid4

# Third party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import (
    HrAbsence,
    HrAbsenceType,
    HrAttendanceDay,
    HrContract,
    HrEmploymentProfile,
    HrPeriod,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

FULL = 462
JANUARY = date(2026, 1, 1)
IN_JANUARY = date(2026, 1, 20)
IN_FEBRUARY = date(2026, 2, 10)

SETTLED = [HrPeriod.State.SUBMITTED, HrPeriod.State.APPROVED, HrPeriod.State.LOCKED]


@pytest.fixture
def person():
    return UserFactory(username=uuid4().hex)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def employed(user, records_attendance=True):
    workspace = WorkspaceFactory(owner=user)
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.ADMIN.value)
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone="Europe/Vienna",
        hire_date=date(2024, 1, 1),
        is_hr_manager=True,
    )
    HrContract.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2024, 1, 1),
        arrangement=HrContract.Arrangement.ONSITE_FULL_TIME,
        records_target_hours=True,
        records_attendance=records_attendance,
        weekly_minutes=2310,
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
    return profile


def month_of(profile, first, state):
    """A month in the given state, with the figures a closed one is refused without."""
    return HrPeriod.objects.create(
        workspace=profile.workspace,
        profile=profile,
        period_start=first,
        period_end=date(first.year, first.month, monthrange(first.year, first.month)[1]),
        state=state,
        target_minutes=9240,
        actual_minutes=9240,
        balance_minutes=0,
    )


def a_kind_of_absence(workspace):
    return HrAbsenceType.objects.create(
        workspace=workspace,
        code=uuid4().hex[:8],
        name_de="Urlaub",
        credits_actual=True,
        consumes_leave_entitlement=True,
    )


class TestNothingIsAddedToASettledMonth:
    @pytest.mark.parametrize("state", SETTLED)
    def test_an_absence_cannot_be_recorded_into_one(self, person, state):
        profile = employed(person)
        month_of(profile, JANUARY, state)

        response = client_for(person).post(
            "/api/hr/absences/",
            {
                "profile_id": str(profile.id),
                "absence_type": str(a_kind_of_absence(profile.workspace).id),
                "start_date": IN_JANUARY.isoformat(),
                "end_date": IN_JANUARY.isoformat(),
            },
            format="json",
        )

        assert response.status_code == 409
        assert not HrAbsence.objects.filter(profile_id=profile.id).exists()

    @pytest.mark.parametrize("state", SETTLED)
    def test_hours_cannot_be_entered_into_one(self, person, state):
        profile = employed(person)
        month_of(profile, JANUARY, state)

        response = client_for(person).post(
            "/api/hr/time-entries/",
            {"profile_id": str(profile.id), "entry_date": IN_JANUARY.isoformat(), "minutes": 240},
            format="json",
        )

        assert response.status_code == 409
        assert not HrTimeEntry.objects.filter(profile_id=profile.id).exists()

    @pytest.mark.parametrize("state", SETTLED)
    def test_an_attendance_day_cannot_be_recorded_into_one(self, person, state):
        profile = employed(person)
        month_of(profile, JANUARY, state)

        response = client_for(person).post(
            "/api/hr/attendance/",
            {
                "profile_id": str(profile.id),
                "work_date": IN_JANUARY.isoformat(),
                "started_at_local": "08:00",
                "ended_at_local": "16:00",
                "break_minutes": 30,
            },
            format="json",
        )

        assert response.status_code == 409
        assert not HrAttendanceDay.objects.filter(profile_id=profile.id).exists()

    def test_the_refusal_names_the_month_and_says_what_to_ask_for(self, person):
        """A 409 that does not say which month is a wall with nothing written on it."""
        profile = employed(person)
        month_of(profile, JANUARY, HrPeriod.State.LOCKED)

        response = client_for(person).post(
            "/api/hr/time-entries/",
            {"profile_id": str(profile.id), "entry_date": IN_JANUARY.isoformat(), "minutes": 60},
            format="json",
        )

        assert "January 2026" in response.json()["error"]
        assert "reopened" in response.json()["error"]

    @pytest.mark.parametrize(
        "state,named",
        [
            (HrPeriod.State.SUBMITTED, "handed_in"),
            (HrPeriod.State.APPROVED, "agreed"),
            (HrPeriod.State.LOCKED, "closed"),
        ],
    )
    def test_the_refusal_carries_a_name_the_screen_can_translate(self, person, state, named):
        """The English sentence is a fallback, not the only thing on offer.

        A month is called something different in every language, and so is the
        state it is in. Sending the date and a name for the state lets the screen
        build the sentence in the reader's own words; picking them here would
        make English the only language the refusal is ever readable in.
        """
        profile = employed(person)
        month_of(profile, JANUARY, state)

        body = (
            client_for(person)
            .post(
                "/api/hr/time-entries/",
                {"profile_id": str(profile.id), "entry_date": IN_JANUARY.isoformat(), "minutes": 60},
                format="json",
            )
            .json()
        )

        assert body["reason"] == "month_settled"
        assert body["month"] == JANUARY.isoformat()
        assert body["month_state"] == named
        # And the English is still there for anything that has no wording for it.
        assert body["error"]

    def test_a_month_still_open_takes_them_as_before(self, person):
        """The guard is about settled months, not about the past."""
        profile = employed(person)
        month_of(profile, JANUARY, HrPeriod.State.OPEN)

        response = client_for(person).post(
            "/api/hr/time-entries/",
            {"profile_id": str(profile.id), "entry_date": IN_JANUARY.isoformat(), "minutes": 240},
            format="json",
        )

        assert response.status_code == 201

    def test_a_month_nobody_has_opened_takes_them_too(self, person):
        """No period row at all is not a settled month; backdated entry depends on it."""
        profile = employed(person)

        response = client_for(person).post(
            "/api/hr/time-entries/",
            {"profile_id": str(profile.id), "entry_date": IN_JANUARY.isoformat(), "minutes": 240},
            format="json",
        )

        assert response.status_code == 201


class TestNothingIsDraggedInOrOut:
    def test_hours_cannot_be_moved_out_of_a_settled_month(self, person):
        """The settled month keeps counting them and the open one counts them again."""
        profile = employed(person)
        month_of(profile, JANUARY, HrPeriod.State.LOCKED)
        entry = HrTimeEntry.objects.create(
            workspace=profile.workspace, profile=profile, entry_date=IN_JANUARY, minutes=240
        )

        response = client_for(person).patch(
            f"/api/hr/time-entries/{entry.id}/",
            {"entry_date": IN_FEBRUARY.isoformat()},
            format="json",
        )

        assert response.status_code == 409
        entry.refresh_from_db()
        assert entry.entry_date == IN_JANUARY

    def test_hours_cannot_be_moved_into_a_settled_month_either(self, person):
        """Arriving is the losing direction — the settled month will never notice."""
        profile = employed(person)
        month_of(profile, JANUARY, HrPeriod.State.LOCKED)
        entry = HrTimeEntry.objects.create(
            workspace=profile.workspace, profile=profile, entry_date=IN_FEBRUARY, minutes=240
        )

        response = client_for(person).patch(
            f"/api/hr/time-entries/{entry.id}/",
            {"entry_date": IN_JANUARY.isoformat()},
            format="json",
        )

        assert response.status_code == 409

    def test_an_absence_reaching_into_a_settled_month_is_refused(self, person):
        """The range is what counts, not where it starts."""
        profile = employed(person)
        month_of(profile, JANUARY, HrPeriod.State.LOCKED)

        response = client_for(person).post(
            "/api/hr/absences/",
            {
                "profile_id": str(profile.id),
                "absence_type": str(a_kind_of_absence(profile.workspace).id),
                "start_date": "2026-01-29",
                "end_date": "2026-02-03",
            },
            format="json",
        )

        assert response.status_code == 409

    def test_a_month_settled_in_the_middle_of_a_range_is_found(self, person):
        """February sits between the two ends and was never asked about before."""
        profile = employed(person)
        month_of(profile, date(2026, 2, 1), HrPeriod.State.LOCKED)

        response = client_for(person).post(
            "/api/hr/absences/",
            {
                "profile_id": str(profile.id),
                "absence_type": str(a_kind_of_absence(profile.workspace).id),
                "start_date": "2026-01-28",
                "end_date": "2026-03-04",
            },
            format="json",
        )

        assert response.status_code == 409

    def test_agreeing_to_an_absence_in_a_settled_month_is_refused(self, person):
        """Approval is what makes it count, so it changes the figure as surely."""
        profile = employed(person)
        month_of(profile, JANUARY, HrPeriod.State.LOCKED)
        absence = HrAbsence.objects.create(
            workspace=profile.workspace,
            profile=profile,
            absence_type=a_kind_of_absence(profile.workspace),
            start_date=IN_JANUARY,
            end_date=IN_JANUARY,
            state=HrAbsence.State.REQUESTED,
        )

        response = client_for(person).post(f"/api/hr/absences/{absence.id}/approve/", {}, format="json")

        assert response.status_code == 409
        absence.refresh_from_db()
        assert absence.state == HrAbsence.State.REQUESTED

    def test_hours_in_a_settled_month_cannot_be_deleted(self, person):
        """Deleting is the same edit, taken to the end."""
        profile = employed(person)
        month_of(profile, JANUARY, HrPeriod.State.LOCKED)
        entry = HrTimeEntry.objects.create(
            workspace=profile.workspace, profile=profile, entry_date=IN_JANUARY, minutes=240
        )

        response = client_for(person).delete(f"/api/hr/time-entries/{entry.id}/")

        assert response.status_code == 409
        assert HrTimeEntry.objects.filter(pk=entry.id).exists()
