# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Correcting a leave year, and changing one after it was agreed.

A figure not yet held as final is a draft: whoever looks after the team corrects
it or deletes it. Once held as final it is what was agreed with the person, so it
stays as it was, and a later change is an adjustment beside it with its reason.
"""

# Python imports
from datetime import date
from uuid import uuid4

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import (
    HrAbsence,
    HrAbsenceType,
    HrAuditLog,
    HrEmploymentProfile,
    HrLeaveAdjustment,
    HrLeaveEntitlement,
    HrWorkSchedule,
)
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

DAY = 480


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
    HrWorkSchedule.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2024, 1, 1),
        monday_minutes=DAY,
        tuesday_minutes=DAY,
        wednesday_minutes=DAY,
        thursday_minutes=DAY,
        friday_minutes=DAY,
    )
    return user, profile


@pytest.fixture
def manager(workspace):
    return employ(workspace, is_hr_manager=True)[0]


@pytest.fixture
def person(workspace):
    return employ(workspace)


def a_year(profile, minutes=3 * DAY, is_final=False, start=date(2026, 1, 1), end=date(2026, 12, 31)):
    return HrLeaveEntitlement.objects.create(
        workspace=profile.workspace,
        profile=profile,
        leave_year_start=start,
        leave_year_end=end,
        entitlement_minutes=minutes,
        is_final=is_final,
    )


def leave_url(profile, row=None, tail=""):
    return f"/api/hr/employees/{profile.id}/leave/" + (f"{row.id}/" if row else "") + tail


class TestCorrectingADraft:
    def test_a_year_not_held_as_final_can_be_corrected(self, manager, person):
        _, profile = person
        row = a_year(profile)
        response = client_for(manager).patch(leave_url(profile, row), {"entitlement_minutes": 8 * DAY}, format="json")
        assert response.status_code == 200, response.json()
        assert response.json()["granted_minutes"] == 8 * DAY
        entry = HrAuditLog.objects.get(profile_id=profile.id, action="leave_year_changed")
        assert entry.changes == {"entitlement_minutes": {"from": 3 * DAY, "to": 8 * DAY}}

    def test_holding_it_as_final_is_filed_as_that(self, manager, person):
        _, profile = person
        row = a_year(profile)
        client_for(manager).patch(leave_url(profile, row), {"is_final": True}, format="json")
        assert HrAuditLog.objects.filter(profile_id=profile.id, action="leave_year_agreed").exists()

    def test_a_year_not_held_as_final_can_be_deleted(self, manager, person):
        _, profile = person
        row = a_year(profile)
        assert client_for(manager).delete(leave_url(profile, row)).status_code == 204
        assert not HrLeaveEntitlement.objects.filter(pk=row.pk).exists()
        entry = HrAuditLog.objects.get(profile_id=profile.id, action="leave_year_deleted")
        assert entry.object_id == row.pk

    def test_moving_a_year_over_another_is_refused(self, manager, person):
        _, profile = person
        a_year(profile, start=date(2025, 1, 1), end=date(2025, 12, 31))
        row = a_year(profile)
        response = client_for(manager).patch(leave_url(profile, row), {"leave_year_start": "2025-06-01"}, format="json")
        assert response.status_code == 400
        assert "leave_year_start" in response.json()

    def test_adding_a_year_over_another_is_refused(self, manager, person):
        _, profile = person
        a_year(profile)
        response = client_for(manager).post(
            leave_url(profile),
            {"leave_year_start": "2026-06-01", "leave_year_end": "2027-05-31", "entitlement_minutes": DAY},
            format="json",
        )
        assert response.status_code == 400

    def test_a_year_ending_before_it_starts_is_refused_not_a_crash(self, manager, person):
        _, profile = person
        row = a_year(profile)
        response = client_for(manager).patch(leave_url(profile, row), {"leave_year_end": "2025-12-31"}, format="json")
        assert response.status_code == 400

    def test_the_adjustments_total_is_not_edited_directly(self, manager, person):
        _, profile = person
        row = a_year(profile)
        client_for(manager).patch(leave_url(profile, row), {"adjustment_minutes": 50 * DAY}, format="json")
        row.refresh_from_db()
        assert row.adjustment_minutes == 0

    def test_the_person_cannot_correct_their_own_leave(self, person):
        user, profile = person
        row = a_year(profile)
        assert (
            client_for(user)
            .patch(leave_url(profile, row), {"entitlement_minutes": 99 * DAY}, format="json")
            .status_code
            == 403
        )
        assert client_for(user).delete(leave_url(profile, row)).status_code == 403


class TestAfterItWasAgreed:
    def test_an_agreed_year_is_neither_edited_nor_deleted(self, manager, person):
        _, profile = person
        row = a_year(profile, is_final=True)
        client = client_for(manager)
        edited = client.patch(leave_url(profile, row), {"entitlement_minutes": 8 * DAY}, format="json")
        assert edited.status_code == 409
        assert edited.json()["reason"] == "leave_year_agreed"
        assert client.delete(leave_url(profile, row)).status_code == 409
        row.refresh_from_db()
        assert row.entitlement_minutes == 3 * DAY

    def test_an_adjustment_changes_what_is_granted_and_keeps_what_was_agreed(self, manager, person):
        _, profile = person
        row = a_year(profile, is_final=True)
        response = client_for(manager).post(
            leave_url(profile, row, "adjustments/"),
            {"minutes": 5 * DAY, "reason": "Five days were missing from the figure"},
            format="json",
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["entitlement_minutes"] == 3 * DAY
        assert body["adjustment_minutes"] == 5 * DAY
        assert body["granted_minutes"] == 8 * DAY
        assert [(a["minutes"], a["reason"]) for a in body["adjustments"]] == [
            (5 * DAY, "Five days were missing from the figure")
        ]
        assert body["adjustments"][0]["created_by_name"]
        entry = HrAuditLog.objects.get(profile_id=profile.id, action="leave_year_adjusted")
        assert entry.reason == "Five days were missing from the figure"

    def test_adjustments_add_up_and_can_take_leave_away(self, manager, person):
        _, profile = person
        row = a_year(profile, is_final=True)
        client = client_for(manager)
        client.post(leave_url(profile, row, "adjustments/"), {"minutes": 2 * DAY, "reason": "a"}, format="json")
        client.post(leave_url(profile, row, "adjustments/"), {"minutes": -DAY, "reason": "b"}, format="json")
        row.refresh_from_db()
        assert row.adjustment_minutes == DAY
        assert HrLeaveAdjustment.objects.filter(entitlement=row).count() == 2

    @pytest.mark.parametrize(
        "payload",
        [
            {"minutes": 0, "reason": "nothing"},
            {"minutes": DAY, "reason": "   "},
            {"minutes": DAY},
            {"minutes": True, "reason": "a flag is not an amount"},
            {"minutes": "480", "reason": "text is not an amount"},
        ],
    )
    def test_an_adjustment_needs_an_amount_and_a_reason(self, manager, person, payload):
        _, profile = person
        row = a_year(profile, is_final=True)
        response = client_for(manager).post(leave_url(profile, row, "adjustments/"), payload, format="json")
        assert response.status_code == 400
        assert not HrLeaveAdjustment.objects.exists()

    def test_the_person_cannot_adjust_their_own_leave(self, person):
        user, profile = person
        row = a_year(profile, is_final=True)
        response = client_for(user).post(
            leave_url(profile, row, "adjustments/"), {"minutes": 10 * DAY, "reason": "mine"}, format="json"
        )
        assert response.status_code == 403


class TestWhatIsLeft:
    def test_each_year_says_what_was_taken_and_what_is_left(self, workspace, manager, person):
        _, profile = person
        a_year(profile, minutes=8 * DAY)
        leave = HrAbsenceType.objects.create(
            workspace=workspace,
            code=uuid4().hex[:8],
            name_de="Urlaub",
            credits_actual=True,
            consumes_leave_entitlement=True,
        )
        HrAbsence.objects.create(
            workspace=workspace,
            profile=profile,
            absence_type=leave,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            state=HrAbsence.State.APPROVED,
        )
        [row] = client_for(manager).get(leave_url(profile)).json()
        assert row["taken_minutes"] == 2 * DAY
        assert row["remaining_minutes"] == 6 * DAY
