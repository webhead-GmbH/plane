# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The endpoints behind the personal view and the manager's month.

The visibility cases matter most here. A permission rule that is correct in
isolation and not actually applied at the endpoint is worse than no rule at all,
so each one is exercised through a real request.
"""

# Python imports
from datetime import date
from uuid import uuid4

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import HrContract, HrEmploymentProfile, HrPeriod, HrWorkSchedule
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

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


def employ(workspace, is_hr_manager=False, records_target=True):
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
        records_target_hours=records_target,
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


class TestMe:
    def test_returns_profile_contract_and_schedule_in_one_request(self, workspace):
        user, profile = employ(workspace)
        response = client_for(user).get(f"/api/hr/workspaces/{workspace.slug}/me/")
        assert response.status_code == 200
        body = response.json()
        assert body["profile"]["id"] == str(profile.id)
        assert body["contract"]["arrangement"] == HrContract.Arrangement.ONSITE_FULL_TIME
        assert body["schedule"]["monday_minutes"] == FULL
        assert body["is_hr_manager"] is False
        assert body["has_running_timer"] is False

    def test_an_administrator_without_an_employment_record_gets_an_empty_profile(self, workspace):
        response = client_for(workspace.owner).get(f"/api/hr/workspaces/{workspace.slug}/me/")
        assert response.status_code == 200
        assert response.json()["profile"] is None
        assert response.json()["is_hr_manager"] is True

    def test_somebody_outside_the_workspace_is_refused(self, workspace):
        outsider = new_user()
        response = client_for(outsider).get(f"/api/hr/workspaces/{workspace.slug}/me/")
        assert response.status_code == 403

    def test_an_anonymous_caller_is_refused(self, workspace):
        response = APIClient().get(f"/api/hr/workspaces/{workspace.slug}/me/")
        assert response.status_code in (401, 403)


class TestPeriods:
    def test_a_recompute_produces_a_month_of_days(self, workspace):
        user, profile = employ(workspace)
        period = HrPeriod.objects.create(
            workspace=workspace,
            profile=profile,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        response = client_for(user).post(
            f"/api/hr/workspaces/{workspace.slug}/periods/{period.id}/recompute/"
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["days"]) == 31
        assert body["target_minutes"] == FULL * 22  # March 2026 has 22 weekdays

    def test_the_day_breakdown_is_readable_on_its_own(self, workspace):
        user, profile = employ(workspace)
        period = HrPeriod.objects.create(
            workspace=workspace,
            profile=profile,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        client = client_for(user)
        client.post(f"/api/hr/workspaces/{workspace.slug}/periods/{period.id}/recompute/")
        response = client.get(f"/api/hr/workspaces/{workspace.slug}/periods/{period.id}/days/")
        assert response.status_code == 200
        assert len(response.json()) == 31

    def test_a_closed_month_refuses_to_be_recomputed(self, workspace):
        user, profile = employ(workspace)
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
        response = client_for(user).post(
            f"/api/hr/workspaces/{workspace.slug}/periods/{period.id}/recompute/"
        )
        assert response.status_code == 409

    def test_one_person_cannot_read_another_persons_month(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        period = HrPeriod.objects.create(
            workspace=workspace,
            profile=colleague,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        response = client_for(user).get(
            f"/api/hr/workspaces/{workspace.slug}/periods/{period.id}/"
        )
        assert response.status_code == 404

    def test_one_person_cannot_read_another_persons_days(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        period = HrPeriod.objects.create(
            workspace=workspace,
            profile=colleague,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        response = client_for(user).get(
            f"/api/hr/workspaces/{workspace.slug}/periods/{period.id}/days/"
        )
        assert response.status_code == 404

    def test_a_manager_can_read_a_colleagues_month(self, workspace):
        manager_user, _ = employ(workspace, is_hr_manager=True)
        _, colleague = employ(workspace)
        period = HrPeriod.objects.create(
            workspace=workspace,
            profile=colleague,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        response = client_for(manager_user).get(
            f"/api/hr/workspaces/{workspace.slug}/periods/{period.id}/"
        )
        assert response.status_code == 200

    def test_listing_defaults_to_your_own_months(self, workspace):
        user, profile = employ(workspace)
        _, colleague = employ(workspace)
        for owner in (profile, colleague):
            HrPeriod.objects.create(
                workspace=workspace,
                profile=owner,
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
            )
        response = client_for(user).get(f"/api/hr/workspaces/{workspace.slug}/periods/")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["profile"] == str(profile.id)

    def test_asking_for_a_colleagues_list_is_refused(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        response = client_for(user).get(
            f"/api/hr/workspaces/{workspace.slug}/periods/?profile_id={colleague.id}"
        )
        assert response.status_code == 404


class TestMalformedParameters:
    """A typo in a query string must not come back as a server error."""

    @pytest.mark.parametrize(
        "query",
        ["?month=13", "?month=0", "?month=-1", "?year=0", "?year=99999999", "?month=abc", "?year="],
    )
    def test_the_personal_view_survives_nonsense(self, workspace, query):
        user, _ = employ(workspace)
        response = client_for(user).get(f"/api/hr/workspaces/{workspace.slug}/me/{query}")
        assert response.status_code == 200

    @pytest.mark.parametrize("query", ["?month=13", "?year=99999999", "?month=0"])
    def test_the_overview_survives_nonsense(self, workspace, query):
        manager_user, _ = employ(workspace, is_hr_manager=True)
        response = client_for(manager_user).get(
            f"/api/hr/workspaces/{workspace.slug}/overview/{query}"
        )
        assert response.status_code == 200

    def test_listing_survives_an_impossible_year(self, workspace):
        user, _ = employ(workspace)
        response = client_for(user).get(
            f"/api/hr/workspaces/{workspace.slug}/periods/?year=99999999"
        )
        assert response.status_code == 200

    def test_a_malformed_person_id_is_not_a_server_error(self, workspace):
        user, _ = employ(workspace)
        response = client_for(user).get(
            f"/api/hr/workspaces/{workspace.slug}/periods/?profile_id=not-a-uuid"
        )
        assert response.status_code in (400, 404)


class TestOverview:
    def test_a_manager_sees_a_row_for_everyone(self, workspace):
        manager_user, _ = employ(workspace, is_hr_manager=True)
        employ(workspace)
        employ(workspace)
        response = client_for(manager_user).get(
            f"/api/hr/workspaces/{workspace.slug}/overview/?year=2026&month=3"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["year"] == 2026
        assert len(body["rows"]) == 3
        assert all("member_display_name" in row for row in body["rows"])

    def test_an_employee_cannot_see_the_overview(self, workspace):
        user, _ = employ(workspace)
        response = client_for(user).get(f"/api/hr/workspaces/{workspace.slug}/overview/")
        assert response.status_code == 403

    def test_the_overview_builds_months_that_did_not_exist_yet(self, workspace):
        manager_user, _ = employ(workspace, is_hr_manager=True)
        assert not HrPeriod.objects.exists()
        response = client_for(manager_user).get(
            f"/api/hr/workspaces/{workspace.slug}/overview/?year=2026&month=3"
        )
        assert response.status_code == 200
        assert HrPeriod.objects.filter(period_start=date(2026, 3, 1)).exists()
