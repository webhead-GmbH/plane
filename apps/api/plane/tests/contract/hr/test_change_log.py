# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Every change to an hour record leaves a trail.

Hours here are freely editable by the person they belong to and by whoever looks
after the team. That is the right arrangement — people correct their own
mistakes — but it means every figure the module produces is only as good as the
trail behind it. A month that came to 142 hours and now comes to 138 has no
answer to the only question worth asking about the difference unless the change
was written down as it happened.

The deletion cases matter most: the row itself can no longer testify to anything
once it is gone, so if the entry is not written at the time it never can be.
"""

# Python imports
from datetime import date
from uuid import uuid4

# Third party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import (
    HrAbsenceType,
    HrAuditLog,
    HrContract,
    HrEmploymentProfile,
    HrWorkSchedule,
)
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

FULL = 462


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
        records_attendance=True,
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


def entries_for(profile, action=None):
    rows = HrAuditLog.objects.filter(profile_id=profile.id)
    return list(rows.filter(action=action) if action else rows)


class TestHoursThatAreNotOnAWorkItem:
    def test_entering_some_is_written_down(self, workspace):
        user, profile = employ(workspace)
        client_for(user).post(
            "/api/hr/time-entries/",
            {"profile_id": str(profile.id), "entry_date": "2026-03-02", "minutes": 120, "category": 30},
            format="json",
        )

        entry = entries_for(profile, "hours_entered")[0]
        assert entry.actor_id == user.id
        assert entry.changes["minutes"] == 120

    def test_changing_the_length_records_both_figures(self, workspace):
        """From and to, not just to. "It says 60" is not an answer to "it said 480"."""
        user, profile = employ(workspace)
        created = client_for(user).post(
            "/api/hr/time-entries/",
            {"profile_id": str(profile.id), "entry_date": "2026-03-02", "minutes": 480, "category": 30},
            format="json",
        )
        client_for(user).patch(
            f"/api/hr/time-entries/{created.data['id']}/", {"minutes": 60}, format="json"
        )

        entry = entries_for(profile, "hours_changed")[0]
        assert entry.changes["minutes"] == {"from": 480, "to": 60}

    def test_deleting_some_keeps_what_they_were(self, workspace):
        """The row cannot testify once it is gone, so the entry is written first."""
        user, profile = employ(workspace)
        created = client_for(user).post(
            "/api/hr/time-entries/",
            {"profile_id": str(profile.id), "entry_date": "2026-03-02", "minutes": 480, "category": 30},
            format="json",
        )
        client_for(user).delete(f"/api/hr/time-entries/{created.data['id']}/")

        entry = entries_for(profile, "hours_removed")[0]
        assert entry.changes["minutes"] == 480
        assert entry.changes["entry_date"] == "2026-03-02"
        assert entry.actor_id == user.id

    def test_hours_entered_by_somebody_else_say_so(self, workspace):
        """From the row alone the two are indistinguishable afterwards."""
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        client_for(manager).post(
            "/api/hr/time-entries/",
            {"profile_id": str(profile.id), "entry_date": "2026-03-02", "minutes": 120, "category": 30},
            format="json",
        )

        entry = entries_for(profile, "hours_entered_for_them")[0]
        # Filed against the person it was about, by the person who did it.
        assert entry.profile_id == profile.id
        assert entry.actor_id == manager.id

    def test_a_refused_change_leaves_nothing_behind(self, workspace):
        """Written on the way out, so an attempt is not mistaken for a change."""
        user, profile = employ(workspace)
        client_for(user).post(
            "/api/hr/time-entries/",
            {"profile_id": str(profile.id), "entry_date": "not a date", "minutes": 120, "category": 30},
            format="json",
        )

        assert entries_for(profile) == []


class TestTimeAway:
    @pytest.fixture
    def leave_type(self, workspace):
        return HrAbsenceType.objects.create(
            workspace=workspace, code=uuid4().hex[:8], name_de="Urlaub", credits_actual=True
        )

    def test_asking_for_leave_is_written_down(self, workspace, leave_type):
        user, profile = employ(workspace)
        client_for(user).post(
            "/api/hr/absences/",
            {
                "profile_id": str(profile.id),
                "absence_type": str(leave_type.id),
                "start_date": "2026-03-02",
                "end_date": "2026-03-06",
            },
            format="json",
        )

        assert entries_for(profile, "absence_created")

    def test_a_decision_records_who_made_it(self, workspace, leave_type):
        manager, _ = employ(workspace, is_hr_manager=True)
        user, profile = employ(workspace)
        created = client_for(user).post(
            "/api/hr/absences/",
            {
                "profile_id": str(profile.id),
                "absence_type": str(leave_type.id),
                "start_date": "2026-03-02",
                "end_date": "2026-03-02",
            },
            format="json",
        )
        client_for(manager).post(f"/api/hr/absences/{created.data['id']}/approve/")

        entry = entries_for(profile, "absence_approved")[0]
        assert entry.actor_id == manager.id
        assert entry.profile_id == profile.id

    def test_a_refusal_keeps_the_reason_given(self, workspace, leave_type):
        manager, _ = employ(workspace, is_hr_manager=True)
        user, profile = employ(workspace)
        created = client_for(user).post(
            "/api/hr/absences/",
            {
                "profile_id": str(profile.id),
                "absence_type": str(leave_type.id),
                "start_date": "2026-03-02",
                "end_date": "2026-03-02",
            },
            format="json",
        )
        client_for(manager).post(
            f"/api/hr/absences/{created.data['id']}/reject/",
            {"reason": "Two people are already away that week"},
            format="json",
        )

        entry = entries_for(profile, "absence_rejected")[0]
        assert entry.reason == "Two people are already away that week"


class TestBeingAtWork:
    def test_recording_a_day_is_written_down(self, workspace):
        user, profile = employ(workspace)
        client_for(user).post(
            "/api/hr/attendance/",
            {
                "profile_id": str(profile.id),
                "work_date": "2026-03-02",
                "started_at_local": "09:00",
                "ended_at_local": "17:00",
                "break_minutes": 30,
            },
            format="json",
        )

        entry = entries_for(profile, "attendance_recorded")[0]
        assert entry.changes["net_minutes"] == 8 * 60 - 30

    def test_correcting_one_records_what_moved(self, workspace):
        user, profile = employ(workspace)
        created = client_for(user).post(
            "/api/hr/attendance/",
            {
                "profile_id": str(profile.id),
                "work_date": "2026-03-02",
                "started_at_local": "09:00",
                "ended_at_local": "17:00",
                "break_minutes": 30,
            },
            format="json",
        )
        client_for(user).patch(
            f"/api/hr/attendance/{created.data['id']}/", {"ended_at_local": "18:00"}, format="json"
        )

        entry = entries_for(profile, "attendance_corrected")[0]
        assert entry.changes["net_minutes"] == {"from": 8 * 60 - 30, "to": 9 * 60 - 30}
        # Only what moved, so the field somebody opened the entry to find is not
        # buried under the ones that did not.
        assert "work_date" not in entry.changes

    def test_removing_a_day_keeps_what_it_said(self, workspace):
        user, profile = employ(workspace)
        created = client_for(user).post(
            "/api/hr/attendance/",
            {
                "profile_id": str(profile.id),
                "work_date": "2026-03-02",
                "started_at_local": "09:00",
                "ended_at_local": "17:00",
                "break_minutes": 30,
            },
            format="json",
        )
        client_for(user).delete(f"/api/hr/attendance/{created.data['id']}/")

        entry = entries_for(profile, "attendance_removed")[0]
        assert entry.changes["work_date"] == "2026-03-02"
        assert entry.changes["net_minutes"] == 8 * 60 - 30
