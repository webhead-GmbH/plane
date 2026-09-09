# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Recording when somebody was at work."""

# Python imports
from datetime import date
from uuid import uuid4

# Third party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import (
    HrAttendanceDay,
    HrContract,
    HrEmploymentProfile,
    HrPeriod,
    HrWorkSchedule,
)
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = pytest.mark.django_db

FULL = 462


def new_user():
    """The shared factory leaves the unique username unset, so a second user collides."""
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


def employ(workspace, records_attendance=True, is_hr_manager=False):
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
    return user, profile


def a_day(**overrides):
    body = {
        "work_date": "2026-03-02",
        "started_at_local": "09:00",
        "ended_at_local": "17:00",
        "break_minutes": 30,
    }
    body.update(overrides)
    return body


class TestRecordingADay:
    def test_a_person_records_their_own_day_and_the_total_is_worked_out(self, workspace):
        user, profile = employ(workspace)
        response = client_for(user).post("/api/hr/attendance/", a_day(profile_id=str(profile.id)), format="json")
        assert response.status_code == 201
        assert response.data["net_minutes"] == 8 * 60 - 30
        # The zone is snapshotted from the person, so moving them later does not
        # rewrite what the day meant.
        assert response.data["local_timezone"] == "Europe/Vienna"

    def test_the_day_reaches_the_month(self, workspace):
        """The ledger already carries attendance; recording one has to rebuild it."""
        user, profile = employ(workspace)
        client_for(user).post("/api/hr/attendance/", a_day(profile_id=str(profile.id)), format="json")
        period = HrPeriod.objects.get(profile=profile, period_start=date(2026, 3, 1))
        assert period.days.get(work_date=date(2026, 3, 2)).attendance_minutes == 8 * 60 - 30

    def test_somebody_it_was_never_turned_on_for_is_refused(self, workspace):
        """Off by default, and the switch exists to withhold exactly this record."""
        user, profile = employ(workspace, records_attendance=False)
        response = client_for(user).post("/api/hr/attendance/", a_day(profile_id=str(profile.id)), format="json")
        assert response.status_code == 409
        assert HrAttendanceDay.objects.count() == 0

    def test_a_time_the_clocks_jumped_over_is_refused_with_a_reason(self, workspace):
        user, profile = employ(workspace)
        response = client_for(user).post(
            "/api/hr/attendance/",
            a_day(profile_id=str(profile.id), work_date="2026-03-29", started_at_local="02:30"),
            format="json",
        )
        assert response.status_code == 400
        assert "forward" in response.data["error"]

    def test_an_end_before_the_start_is_refused(self, workspace):
        user, profile = employ(workspace)
        response = client_for(user).post(
            "/api/hr/attendance/",
            a_day(profile_id=str(profile.id), started_at_local="17:00", ended_at_local="09:00"),
            format="json",
        )
        assert response.status_code == 400

    def test_a_day_can_be_left_open(self, workspace):
        """Somebody who has started and not finished has no total yet."""
        user, profile = employ(workspace)
        response = client_for(user).post(
            "/api/hr/attendance/",
            a_day(profile_id=str(profile.id), ended_at_local=None),
            format="json",
        )
        assert response.status_code == 201
        assert response.data["net_minutes"] == 0

    def test_where_the_day_was_worked_is_recorded(self, workspace):
        """Days worked away from the premises are counted for the year."""
        user, profile = employ(workspace)
        response = client_for(user).post(
            "/api/hr/attendance/",
            a_day(profile_id=str(profile.id), work_location=HrAttendanceDay.WorkLocation.HOME),
            format="json",
        )
        assert response.status_code == 201
        assert response.data["work_location"] == HrAttendanceDay.WorkLocation.HOME


class TestChangingADay:
    def test_correcting_a_day_says_it_was_corrected(self, workspace):
        user, profile = employ(workspace)
        created = client_for(user).post("/api/hr/attendance/", a_day(profile_id=str(profile.id)), format="json")
        response = client_for(user).patch(
            f"/api/hr/attendance/{created.data['id']}/", {"ended_at_local": "18:00"}, format="json"
        )
        assert response.status_code == 200
        assert response.data["net_minutes"] == 9 * 60 - 30
        assert response.data["recording_method"] == HrAttendanceDay.RecordingMethod.CORRECTED

    def test_a_day_in_a_closed_month_refuses_to_change(self, workspace):
        user, profile = employ(workspace)
        created = client_for(user).post("/api/hr/attendance/", a_day(profile_id=str(profile.id)), format="json")
        HrAttendanceDay.objects.filter(pk=created.data["id"]).update(
            locked_period=HrPeriod.objects.get(profile=profile, period_start=date(2026, 3, 1))
        )
        response = client_for(user).patch(
            f"/api/hr/attendance/{created.data['id']}/", {"ended_at_local": "18:00"}, format="json"
        )
        assert response.status_code == 409

    def test_removing_a_day_takes_it_out_of_the_month_too(self, workspace):
        user, profile = employ(workspace)
        created = client_for(user).post("/api/hr/attendance/", a_day(profile_id=str(profile.id)), format="json")
        response = client_for(user).delete(f"/api/hr/attendance/{created.data['id']}/")
        assert response.status_code == 204
        period = HrPeriod.objects.get(profile=profile, period_start=date(2026, 3, 1))
        assert not period.days.get(work_date=date(2026, 3, 2)).attendance_minutes


class TestWhoCanSeeIt:
    def test_one_person_cannot_read_anothers(self, workspace):
        user, _ = employ(workspace)
        colleague, other = employ(workspace)
        client_for(colleague).post("/api/hr/attendance/", a_day(profile_id=str(other.id)), format="json")
        response = client_for(user).get(f"/api/hr/attendance/?profile_id={other.id}")
        assert response.status_code == 200
        assert response.data == []

    def test_a_manager_sees_the_team(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        user, profile = employ(workspace)
        client_for(user).post("/api/hr/attendance/", a_day(profile_id=str(profile.id)), format="json")
        response = client_for(manager).get(f"/api/hr/attendance/?profile_id={profile.id}")
        assert response.status_code == 200
        assert len(response.data) == 1


class TestTheYearsTeleworkCount:
    """Days worked away from the premises, counted for the year.

    A payroll input rather than a convenience, and one that cannot be
    reconstructed afterwards from anything else the system holds.
    """

    def test_days_at_home_are_counted_and_reach_the_personal_view(self, workspace):
        user, profile = employ(workspace)
        client = client_for(user)
        for day_of_month in (2, 3):
            client.post(
                "/api/hr/attendance/",
                a_day(
                    profile_id=str(profile.id),
                    work_date=f"2026-03-{day_of_month:02d}",
                    work_location=HrAttendanceDay.WorkLocation.HOME,
                ),
                format="json",
            )

        response = client.get("/api/hr/me/?year=2026&month=3")
        assert response.status_code == 200
        assert response.data["telework_days_this_year"] == 2

    def test_days_at_the_office_are_not(self, workspace):
        user, profile = employ(workspace)
        client = client_for(user)
        client.post("/api/hr/attendance/", a_day(profile_id=str(profile.id)), format="json")
        assert client.get("/api/hr/me/?year=2026&month=3").data["telework_days_this_year"] == 0

    def test_last_year_is_not_this_year(self, workspace):
        user, profile = employ(workspace)
        client = client_for(user)
        client.post(
            "/api/hr/attendance/",
            a_day(profile_id=str(profile.id), work_date="2025-03-03", work_location=HrAttendanceDay.WorkLocation.HOME),
            format="json",
        )
        assert client.get("/api/hr/me/?year=2026&month=3").data["telework_days_this_year"] == 0

    def test_nothing_is_counted_where_attendance_is_not_kept(self, workspace):
        """Null rather than zero: there is no count, and zero would read as one."""
        user, _ = employ(workspace, records_attendance=False)
        response = client_for(user).get("/api/hr/me/?year=2026&month=3")
        assert response.data["telework_days_this_year"] is None
