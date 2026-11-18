# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the project identifier availability check.

A refusal that only says "Identifier already exists" leaves a person hunting through projects for the one
that holds it, so the answer names the project, its identifier now (a reservation outlives a change of
it), and whether it is archived. A private project's name goes only to those who may see it.
"""

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import ProjectIdentifier, ProjectNetwork
from plane.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory, WorkspaceMemberFactory

ADMIN, MEMBER = 20, 15

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def _url(workspace):
    return f"/api/workspaces/{workspace.slug}/project-identifiers/"


def _client(workspace, role):
    user = UserFactory()
    WorkspaceMemberFactory(workspace=workspace, member=user, role=role)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


def _reserved(workspace, identifier, network=ProjectNetwork.SECRET.value, **fields):
    project = ProjectFactory(workspace=workspace, identifier=identifier, network=network, **fields)
    ProjectIdentifier.objects.create(name=identifier, project=project, workspace=workspace)
    return project


class TestWhoHoldsAnIdentifier:
    def test_a_free_identifier_has_no_holder(self, workspace):
        _, client = _client(workspace, MEMBER)
        body = client.get(_url(workspace), {"name": "free"}).json()
        assert body == {"exists": 0, "identifiers": []}

    def test_a_workspace_admin_is_told_the_project_even_when_it_is_private(self, workspace):
        project = _reserved(workspace, "ATTN", name="Attn Seekr")
        _, client = _client(workspace, ADMIN)
        [holder] = client.get(_url(workspace), {"name": "attn"}).json()["identifiers"]
        assert holder["project"] == str(project.id)
        assert holder["project_name"] == "Attn Seekr"
        assert holder["project_identifier"] == "ATTN"
        assert holder["project_archived"] is False

    def test_a_member_is_told_the_name_of_a_public_project(self, workspace):
        _reserved(workspace, "OPEN", network=ProjectNetwork.PUBLIC.value, name="Open one")
        _, client = _client(workspace, MEMBER)
        [holder] = client.get(_url(workspace), {"name": "OPEN"}).json()["identifiers"]
        assert holder["project_name"] == "Open one"

    def test_a_member_is_told_the_name_of_a_private_project_they_belong_to(self, workspace):
        project = _reserved(workspace, "MINE", name="Mine")
        user, client = _client(workspace, MEMBER)
        ProjectMemberFactory(project=project, member=user, role=MEMBER)
        [holder] = client.get(_url(workspace), {"name": "MINE"}).json()["identifiers"]
        assert holder["project_name"] == "Mine"

    def test_a_member_is_not_told_the_name_of_a_private_project_they_are_outside(self, workspace):
        project = _reserved(workspace, "SECRET", name="Hidden client")
        _, client = _client(workspace, MEMBER)
        response = client.get(_url(workspace), {"name": "SECRET"})
        assert response.status_code == status.HTTP_200_OK
        [holder] = response.json()["identifiers"]
        # That it is taken, and by which project, is known; what it is called and does not leave.
        assert holder["project"] == str(project.id)
        assert holder["project_name"] is None
        assert holder["project_identifier"] is None
        assert holder["project_archived"] is None
        assert "Hidden client" not in response.content.decode()

    def test_an_archived_project_is_said_to_be_archived(self, workspace):
        _reserved(workspace, "OLD", name="Old one", archived_at=timezone.now())
        _, client = _client(workspace, ADMIN)
        [holder] = client.get(_url(workspace), {"name": "OLD"}).json()["identifiers"]
        assert holder["project_archived"] is True

    def test_a_reservation_outlives_a_change_of_the_identifier(self, workspace):
        project = _reserved(workspace, "T209", name="Renumbered")
        project.identifier = "T210"
        project.save()
        _, client = _client(workspace, ADMIN)
        [holder] = client.get(_url(workspace), {"name": "T209"}).json()["identifiers"]
        assert holder["project"] == str(project.id)
        assert (holder["name"], holder["project_identifier"]) == ("T209", "T210")
        # Its current identifier is not reserved by the table at all.
        assert client.get(_url(workspace), {"name": "T210"}).json()["exists"] == 0

    def test_a_name_is_required(self, workspace):
        _, client = _client(workspace, MEMBER)
        assert client.get(_url(workspace), {"name": " "}).status_code == status.HTTP_400_BAD_REQUEST
