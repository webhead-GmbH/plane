# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Hours and assignments that catch up with the CRM without anybody saving each work item.

Somebody deactivated in the CRM before their CRM staff id was set in Plane stops
matching: their new hours land in the "could not be attached" table and they are
dropped from the task's assignees. Setting the id afterwards used to change
nothing until each work item happened to be saved again.
"""

# Python imports
from datetime import date, timedelta
from unittest import mock
from uuid import uuid4

# Third-party imports
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

# Module imports
from plane.bgtasks.crm_sync_task import resync_member_to_crm, resync_stranded_crm_hours
from plane.db.models import (
    CrmIntegration,
    CrmTaskLink,
    CrmTimerLink,
    Issue,
    IssueAssignee,
    IssueWorkLog,
    State,
    WorkspaceMember,
)
from plane.hr.models import HrContract, HrEmploymentProfile
from plane.tests.factories import (
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    WorkspaceFactory,
    WorkspaceMemberFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

EMAIL = "person@example.com"


@pytest.fixture
def setup():
    """A workspace mirrored to the CRM, and work items in every state that matters."""
    owner = UserFactory(username=uuid4().hex)
    workspace = WorkspaceFactory(owner=owner)
    person = UserFactory(username=uuid4().hex, email=EMAIL)
    colleague = UserFactory(username=uuid4().hex, email="colleague@example.com")
    for user in (person, colleague):
        WorkspaceMemberFactory(workspace=workspace, member=user, role=15)
    project = ProjectFactory(workspace=workspace, created_by=owner, updated_by=owner)
    for user in (person, colleague):
        ProjectMemberFactory(project=project, member=user, role=15)
    state = State.objects.create(name="Doing", project=project, workspace=workspace, group="started")

    def issue(name, crm_task_id=None):
        row = Issue.objects.create(project=project, workspace=workspace, name=name, state=state)
        if crm_task_id:
            CrmTaskLink.objects.create(workspace=workspace, issue=row, crm_task_id=crm_task_id, crm_project_id=1)
        return row

    stranded = issue("Hours that never reached the CRM", 501)
    assigned = issue("Assigned, no hours", 502)
    unlinked = issue("Not mirrored to the CRM")
    mirrored = issue("Hours already in the CRM", 503)
    theirs = issue("Somebody else's hours", 504)

    # Written in bulk so the save signals do not try to reach a CRM that does not exist.
    worklogs = IssueWorkLog.objects.bulk_create(
        [
            IssueWorkLog(issue=row, logged_by=user, project=project, workspace=workspace, duration=3600)
            for row, user in ((stranded, person), (unlinked, person), (mirrored, person), (theirs, colleague))
        ]
    )
    CrmTimerLink.objects.create(workspace=workspace, worklog=worklogs[2], crm_timer_id=900)
    IssueAssignee.objects.bulk_create(
        [IssueAssignee(issue=assigned, assignee=person, project=project, workspace=workspace)]
    )

    integration = CrmIntegration(workspace=workspace, crm_api_url="https://crm.example.com")
    integration.set_api_key("key")
    integration.save()
    return {
        "workspace": workspace,
        "person": person,
        "colleague": colleague,
        "stranded": stranded,
        "assigned": assigned,
        "theirs": theirs,
        "integration": integration,
        "worklogs": worklogs,
    }


def queued(call):
    return {args[0] for args, _ in call.call_args_list}


class TestAfterTheirCrmIdChanged:
    def test_their_stranded_hours_and_their_tasks_are_synced_again(self, setup):
        with mock.patch("plane.bgtasks.crm_sync_task.sync_issue_to_crm.delay") as sync:
            resync_member_to_crm(str(setup["person"].id))

        assert queued(sync) == {str(setup["stranded"].id), str(setup["assigned"].id)}

    def test_nothing_happens_without_an_active_integration(self, setup):
        CrmIntegration.objects.filter(pk=setup["integration"].pk).update(is_active=False)

        with mock.patch("plane.bgtasks.crm_sync_task.sync_issue_to_crm.delay") as sync:
            resync_member_to_crm(str(setup["person"].id))

        assert not sync.called

    def test_a_deleted_hour_is_not_a_reason_to_sync(self, setup):
        IssueWorkLog.objects.filter(issue=setup["stranded"]).update(deleted_at=timezone.now())

        with mock.patch("plane.bgtasks.crm_sync_task.sync_issue_to_crm.delay") as sync:
            resync_member_to_crm(str(setup["person"].id))

        assert queued(sync) == {str(setup["assigned"].id)}


class TestTheHourlySweep:
    def test_hours_whose_author_now_has_a_crm_account_are_sent_on(self, setup):
        with (
            mock.patch("plane.bgtasks.crm_sync_task._crm_staff_by_email", return_value={EMAIL: 7}),
            mock.patch("plane.bgtasks.crm_sync_task.sync_issue_to_crm.delay") as sync,
        ):
            resync_stranded_crm_hours()

        # Only the mirrored work item with hours by somebody who matches now.
        assert queued(sync) == {str(setup["stranded"].id)}

    def test_a_crm_staff_id_set_in_plane_counts_as_a_match(self, setup):
        WorkspaceMember.objects.filter(member=setup["colleague"]).update(crm_staff_id=8)

        with (
            mock.patch("plane.bgtasks.crm_sync_task._crm_staff_by_email", return_value={}),
            mock.patch("plane.bgtasks.crm_sync_task.sync_issue_to_crm.delay") as sync,
        ):
            resync_stranded_crm_hours()

        assert queued(sync) == {str(setup["theirs"].id)}

    def test_nobody_who_still_cannot_be_matched_is_synced(self, setup):
        with (
            mock.patch("plane.bgtasks.crm_sync_task._crm_staff_by_email", return_value={}),
            mock.patch("plane.bgtasks.crm_sync_task.sync_issue_to_crm.delay") as sync,
        ):
            resync_stranded_crm_hours()

        assert not sync.called

    def test_an_unreadable_staff_list_waits_for_the_next_hour(self, setup):
        with (
            mock.patch("plane.bgtasks.crm_sync_task._crm_staff_by_email", return_value=None),
            mock.patch("plane.bgtasks.crm_sync_task.sync_issue_to_crm.delay") as sync,
        ):
            resync_stranded_crm_hours()

        assert not sync.called

    def test_old_hours_are_left_alone(self, setup):
        IssueWorkLog.objects.update(created_at=timezone.now() - timedelta(days=45))

        with (
            mock.patch("plane.bgtasks.crm_sync_task._crm_staff_by_email", return_value={EMAIL: 7}) as staff,
            mock.patch("plane.bgtasks.crm_sync_task.sync_issue_to_crm.delay") as sync,
        ):
            resync_stranded_crm_hours()

        assert not sync.called
        # With nothing stranded the CRM is not even asked.
        assert not staff.called


class TestSavingTheIdOnPeople:
    @pytest.fixture
    def manager_client(self, setup):
        manager = UserFactory(username=uuid4().hex)
        WorkspaceMemberFactory(workspace=setup["workspace"], member=manager, role=15)
        HrEmploymentProfile.objects.create(
            workspace=setup["workspace"],
            member=manager,
            timezone="Europe/Vienna",
            hire_date=date(2024, 1, 1),
            is_hr_manager=True,
        )
        client = APIClient()
        client.force_authenticate(user=manager)
        return client

    @pytest.fixture
    def profile(self, setup):
        profile = HrEmploymentProfile.objects.create(
            workspace=setup["workspace"], member=setup["person"], timezone="Europe/Vienna", hire_date=date(2024, 1, 1)
        )
        HrContract.objects.create(
            workspace=setup["workspace"],
            profile=profile,
            valid_from=date(2024, 1, 1),
            arrangement=HrContract.Arrangement.ONSITE_FULL_TIME,
            records_target_hours=True,
        )
        return profile

    def test_setting_it_brings_their_work_up_to_date(
        self, setup, manager_client, profile, django_capture_on_commit_callbacks
    ):
        with (
            mock.patch("plane.bgtasks.crm_sync_task.resync_member_to_crm.delay") as resync,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = manager_client.patch(f"/api/hr/employees/{profile.id}/", {"crm_staff_id": 7}, format="json")

        assert response.status_code == 200
        resync.assert_called_once_with(str(setup["person"].id))

    def test_saving_the_same_id_again_changes_nothing(
        self, setup, manager_client, profile, django_capture_on_commit_callbacks
    ):
        WorkspaceMember.objects.filter(member=setup["person"]).update(crm_staff_id=7)

        with (
            mock.patch("plane.bgtasks.crm_sync_task.resync_member_to_crm.delay") as resync,
            django_capture_on_commit_callbacks(execute=True),
        ):
            manager_client.patch(f"/api/hr/employees/{profile.id}/", {"crm_staff_id": 7}, format="json")

        assert not resync.called

    def test_clearing_it_syncs_too(self, setup, manager_client, profile, django_capture_on_commit_callbacks):
        WorkspaceMember.objects.filter(member=setup["person"]).update(crm_staff_id=7)

        with (
            mock.patch("plane.bgtasks.crm_sync_task.resync_member_to_crm.delay") as resync,
            django_capture_on_commit_callbacks(execute=True),
        ):
            manager_client.patch(f"/api/hr/employees/{profile.id}/", {"crm_staff_id": None}, format="json")

        resync.assert_called_once_with(str(setup["person"].id))

    def test_a_save_without_the_id_does_not_sync(
        self, setup, manager_client, profile, django_capture_on_commit_callbacks
    ):
        with (
            mock.patch("plane.bgtasks.crm_sync_task.resync_member_to_crm.delay") as resync,
            django_capture_on_commit_callbacks(execute=True),
        ):
            manager_client.patch(f"/api/hr/employees/{profile.id}/", {"timezone": "Europe/Berlin"}, format="json")

        assert not resync.called

    # The button on their row, for an id saved before saving one did this by itself.

    def test_the_button_sends_their_work_again(self, setup, manager_client, profile):
        with mock.patch("plane.bgtasks.crm_sync_task.resync_member_to_crm.delay") as resync:
            response = manager_client.post(f"/api/hr/employees/{profile.id}/crm-resync/")

        assert response.status_code == 200
        assert response.json() == {"connected": True, "work_items": 2}
        resync.assert_called_once_with(str(setup["person"].id))

    def test_the_button_says_when_nothing_of_theirs_is_waiting(self, setup, manager_client, profile):
        IssueWorkLog.objects.filter(logged_by=setup["person"]).delete()
        IssueAssignee.objects.filter(assignee=setup["person"]).delete()

        with mock.patch("plane.bgtasks.crm_sync_task.resync_member_to_crm.delay") as resync:
            response = manager_client.post(f"/api/hr/employees/{profile.id}/crm-resync/")

        assert response.json() == {"connected": True, "work_items": 0}
        assert not resync.called

    def test_the_button_says_when_no_workspace_of_theirs_is_connected(self, setup, manager_client, profile):
        CrmIntegration.objects.filter(pk=setup["integration"].pk).update(is_active=False)

        with mock.patch("plane.bgtasks.crm_sync_task.resync_member_to_crm.delay") as resync:
            response = manager_client.post(f"/api/hr/employees/{profile.id}/crm-resync/")

        assert response.json() == {"connected": False, "work_items": 0}
        assert not resync.called

    def test_only_whoever_looks_after_the_team_can_press_it(self, setup, profile):
        client = APIClient()
        client.force_authenticate(user=setup["person"])

        with mock.patch("plane.bgtasks.crm_sync_task.resync_member_to_crm.delay") as resync:
            response = client.post(f"/api/hr/employees/{profile.id}/crm-resync/")

        assert response.status_code == 403
        assert not resync.called
