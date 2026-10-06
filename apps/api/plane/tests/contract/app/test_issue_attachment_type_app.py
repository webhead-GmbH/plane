# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""POST /api/assets/v2/.../issues/{issue_id}/attachments/ for a file sent without a type.

The web client sends the type it reads from the file's content, which is empty for
plain text. The endpoint answered "Invalid file type." to every .txt, .csv and .md.
"""

import pytest
from rest_framework import status

from plane.db.models import FileAsset, Issue, Project, ProjectMember, State


@pytest.fixture
def issue(db, workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    state = State.objects.create(name="Todo", project=project, workspace=workspace, group="backlog", default=True)
    return Issue.objects.create(name="I", workspace=workspace, project=project, state=state, created_by=create_user)


def url(workspace, issue):
    return f"/api/assets/v2/workspaces/{workspace.slug}/projects/{issue.project_id}/issues/{issue.id}/attachments/"


@pytest.mark.contract
@pytest.mark.django_db
class TestAttachingAFileSentWithoutAType:
    @pytest.mark.parametrize(
        "name, expected",
        [("notes.txt", "text/plain"), ("export.csv", "text/csv"), ("README.md", "text/markdown")],
    )
    def test_a_plain_text_file_is_accepted_under_the_type_its_name_gives(
        self, session_client, workspace, issue, name, expected
    ):
        response = session_client.post(url(workspace, issue), {"name": name, "type": "", "size": 120}, format="json")

        assert response.status_code == status.HTTP_200_OK
        # The upload is signed for that type, and the attachment is stored under it.
        assert response.data["upload_data"]["fields"]["Content-Type"] == expected
        assert FileAsset.objects.get(id=response.data["asset_id"]).attributes["type"] == expected

    def test_a_file_whose_name_gives_no_allowed_type_is_still_refused(self, session_client, workspace, issue):
        response = session_client.post(
            url(workspace, issue), {"name": "page.html", "type": "", "size": 120}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not FileAsset.objects.filter(issue_id=issue.id).exists()

    def test_a_declared_type_that_is_not_allowed_is_not_rescued_by_the_name(self, session_client, workspace, issue):
        response = session_client.post(
            url(workspace, issue),
            {"name": "notes.txt", "type": "application/x-msdownload", "size": 120},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not FileAsset.objects.filter(issue_id=issue.id).exists()

    def test_a_declared_type_is_kept(self, session_client, workspace, issue):
        response = session_client.post(
            url(workspace, issue), {"name": "notes.txt", "type": "image/png", "size": 120}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert FileAsset.objects.get(id=response.data["asset_id"]).attributes["type"] == "image/png"
