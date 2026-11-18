# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for what changing a Project ID would do in the CRM, said before it is saved.

With the CRM mapped by identifier the Project ID is the CRM project number: changing it moves the project's
CRM tasks, with their timers and hours, to another CRM project. The number shown has to be the number that
actually moves, and nobody but a project admin is told it.
"""

from unittest import mock

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.app.permissions import ROLE
from plane.db.models import CrmIntegration, CrmTaskLink, Issue, Project, State
from plane.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory, WorkspaceMemberFactory
from plane.utils.crm_client import CrmApiError

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

CLIENT = "plane.app.views.crm_integration.identifier_change.CrmApiClient"
CRM_PROJECTS = [{"id": "209", "name": "ATTN-SEEKR Webseite"}, {"id": "210", "name": "SOHO 2"}]


@pytest.fixture
def crm_projects():
    with mock.patch(CLIENT) as client:
        client.return_value.get_projects.return_value = CRM_PROJECTS
        yield client


@pytest.fixture
def setup(workspace, create_user):
    project = ProjectFactory(workspace=workspace, name="ATTN", identifier="209")
    ProjectMemberFactory(project=project, member=create_user, role=ROLE.ADMIN.value)
    state = State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted")
    issues = [
        Issue.objects.create(project=project, workspace=workspace, name=f"Task {n}", state=state) for n in range(3)
    ]
    for number, issue in enumerate(issues):
        CrmTaskLink.objects.create(workspace=workspace, issue=issue, crm_task_id=500 + number, crm_project_id=209)
    integration = CrmIntegration(
        workspace=workspace,
        crm_api_url="https://crm.example.com",
        is_active=True,
        project_mapping_source=CrmIntegration.ProjectMappingSource.IDENTIFIER,
    )
    integration.set_api_key("key")
    integration.save()
    return {"workspace": workspace, "project": project, "integration": integration, "issues": issues}


def _url(setup):
    return f"/api/workspaces/{setup['workspace'].slug}/projects/{setup['project'].id}/identifier-change/"


def _ask(client, setup, identifier):
    return client.get(_url(setup), {"identifier": identifier})


class TestWhatAProjectIDChangeDoesInTheCrm:
    def test_it_says_how_many_tasks_move_and_to_which_crm_project(self, session_client, setup, crm_projects):
        body = _ask(session_client, setup, "210").json()
        assert body["crm"] == {"current": 209, "target": 210, "tasks": 3, "target_name": "SOHO 2"}

    def test_tasks_already_in_the_new_project_do_not_count(self, session_client, setup, crm_projects):
        CrmTaskLink.objects.filter(crm_task_id=500).update(crm_project_id=210)
        assert _ask(session_client, setup, "210").json()["crm"]["tasks"] == 2

    def test_the_number_is_the_number_the_sync_will_move(self, session_client, setup, crm_projects):
        from plane.bgtasks.crm_sync_task import remap_project_crm_tasks

        said = _ask(session_client, setup, "210").json()["crm"]["tasks"]
        Project.objects.filter(pk=setup["project"].pk).update(identifier="210")
        with mock.patch("plane.bgtasks.crm_sync_task.move_crm_task_to_crm_project.delay") as move:
            remap_project_crm_tasks(str(setup["project"].pk))
        assert move.call_count == said == 3

    def test_a_name_the_crm_cannot_give_is_left_out_and_the_answer_still_comes(self, session_client, setup):
        with mock.patch(CLIENT) as client:
            client.return_value.get_projects.side_effect = CrmApiError("down")
            response = _ask(session_client, setup, "210")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["crm"]["target_name"] is None
        assert response.json()["crm"]["tasks"] == 3

    def test_a_number_that_is_not_a_crm_project_stops_the_project_syncing(self, session_client, setup, crm_projects):
        body = _ask(session_client, setup, "ATTN").json()
        assert body["crm"] == {"current": 209, "target": None, "tasks": 0, "target_name": None}

    def test_a_project_that_was_not_synced_starts_to_be(self, session_client, setup, crm_projects):
        Project.objects.filter(pk=setup["project"].pk).update(identifier="ATTN")
        CrmTaskLink.objects.all().delete()
        body = _ask(session_client, setup, "209").json()
        assert body["crm"] == {"current": None, "target": 209, "tasks": 0, "target_name": None}

    def test_nothing_changes_between_two_names_that_are_not_numbers(self, session_client, setup, crm_projects):
        Project.objects.filter(pk=setup["project"].pk).update(identifier="ATTN")
        assert _ask(session_client, setup, "ATT").json()["crm"] is None

    def test_the_same_id_changes_nothing(self, session_client, setup, crm_projects):
        assert _ask(session_client, setup, "209").json() == {"crm": None, "drive": None}

    def test_the_crm_is_not_involved_when_it_maps_by_custom_field(self, session_client, setup, crm_projects):
        CrmIntegration.objects.filter(pk=setup["integration"].pk).update(
            project_mapping_source=CrmIntegration.ProjectMappingSource.CUSTOM_FIELD
        )
        assert _ask(session_client, setup, "210").json()["crm"] is None

    def test_the_crm_is_not_involved_when_the_sync_is_off(self, session_client, setup, crm_projects):
        CrmIntegration.objects.filter(pk=setup["integration"].pk).update(is_active=False)
        assert _ask(session_client, setup, "210").json()["crm"] is None

    def test_it_asks_the_crm_nothing_when_no_task_would_move(self, session_client, setup, crm_projects):
        CrmTaskLink.objects.all().delete()
        assert _ask(session_client, setup, "210").json()["crm"]["target_name"] is None
        crm_projects.return_value.get_projects.assert_not_called()

    def test_an_identifier_is_required(self, session_client, setup, crm_projects):
        assert _ask(session_client, setup, " ").status_code == status.HTTP_400_BAD_REQUEST

    def test_only_a_project_admin_is_told(self, setup, crm_projects):
        member = UserFactory()
        WorkspaceMemberFactory(workspace=setup["workspace"], member=member, role=ROLE.MEMBER.value)
        ProjectMemberFactory(project=setup["project"], member=member, role=ROLE.MEMBER.value)
        client = APIClient()
        client.force_authenticate(user=member)
        assert _ask(client, setup, "210").status_code == status.HTTP_403_FORBIDDEN
