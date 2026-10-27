# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""An upload counts as done only when its file is in storage.

The browser asks for an upload link (which creates the record), sends the file to
storage, then confirms. When storage refused the file (it was full, on the live
server) the record stayed unconfirmed, yet the work item's attachment list still
showed it and its download answered "The asset is not uploaded." And when the
confirmation alone was lost, a file that was stored stayed out of reach.

These run against the test stack's real storage server.
"""

from io import BytesIO
from unittest import mock
from uuid import uuid4

import pytest
from django.conf import settings
from rest_framework import status

from plane.db.models import FileAsset, Issue, Project, ProjectMember, State
from plane.settings.storage import S3Storage, StorageUnavailable


@pytest.fixture
def issue(db, workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    state = State.objects.create(name="Todo", project=project, workspace=workspace, group="backlog", default=True)
    return Issue.objects.create(name="I", workspace=workspace, project=project, state=state, created_by=create_user)


@pytest.fixture(autouse=True)
def _no_activity():
    with (
        mock.patch("plane.app.views.issue.attachment.issue_activity") as activity,
        mock.patch("plane.app.views.issue.attachment.base_host", return_value="http://testserver"),
    ):
        yield activity


def attachments_url(workspace, issue, pk=None):
    base = f"/api/assets/v2/workspaces/{workspace.slug}/projects/{issue.project_id}/issues/{issue.id}/attachments/"
    return f"{base}{pk}/" if pk else base


def attachment(workspace, issue, user, *, is_uploaded=False, name="report.pdf"):
    asset = FileAsset(
        attributes={"name": name, "type": "application/pdf", "size": 3},
        asset=f"{workspace.id}/{uuid4().hex}-{name}",
        size=3,
        workspace=workspace,
        project_id=issue.project_id,
        issue=issue,
        entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
        is_uploaded=is_uploaded,
    )
    asset.save(created_by_id=user.id)
    return asset


def store(asset, content=b"pdf"):
    """Put the asset's file in storage, as the browser's upload does."""
    assert S3Storage().upload_file(BytesIO(content), asset.asset.name, "application/pdf")


@pytest.mark.contract
@pytest.mark.django_db
class TestConfirmingAnUpload:
    def test_a_file_storage_never_received_is_not_confirmed(self, session_client, workspace, issue, create_user):
        asset = attachment(workspace, issue, create_user)

        response = session_client.patch(attachments_url(workspace, issue, asset.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "UPLOAD_NOT_FOUND"
        asset.refresh_from_db()
        assert asset.is_uploaded is False

    def test_a_stored_file_is_confirmed_with_what_storage_knows_of_it(
        self, session_client, workspace, issue, create_user, _no_activity
    ):
        asset = attachment(workspace, issue, create_user)
        store(asset, b"twelve bytes")

        response = session_client.patch(attachments_url(workspace, issue, asset.id))

        assert response.status_code == status.HTTP_204_NO_CONTENT
        asset.refresh_from_db()
        assert asset.is_uploaded is True
        assert asset.storage_metadata["ContentLength"] == 12
        assert _no_activity.delay.call_count == 1

    def test_when_storage_cannot_be_asked_the_upload_is_taken_as_done(
        self, session_client, workspace, issue, create_user
    ):
        # The browser just stored the file; turning it away now could lose it
        asset = attachment(workspace, issue, create_user)

        with mock.patch("plane.utils.asset_upload.find_stored_file", side_effect=StorageUnavailable("down")):
            response = session_client.patch(attachments_url(workspace, issue, asset.id))

        assert response.status_code == status.HTTP_204_NO_CONTENT
        asset.refresh_from_db()
        assert asset.is_uploaded is True

    def test_a_workspace_asset_is_checked_the_same_way(self, session_client, workspace, create_user):
        asset = FileAsset(
            attributes={"name": "logo.png", "type": "image/png", "size": 3},
            asset=f"{workspace.id}/{uuid4().hex}-logo.png",
            size=3,
            workspace=workspace,
            entity_type=FileAsset.EntityTypeContext.WORKSPACE_LOGO,
        )
        asset.save(created_by_id=create_user.id)
        url = f"/api/assets/v2/workspaces/{workspace.slug}/{asset.id}/"

        response = session_client.patch(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        workspace.refresh_from_db()
        assert workspace.logo_asset_id is None

        store(asset)
        response = session_client.patch(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        workspace.refresh_from_db()
        assert workspace.logo_asset_id == asset.id


@pytest.mark.contract
@pytest.mark.django_db
class TestDownloadingAnUpload:
    def test_a_stored_file_whose_confirmation_was_lost_is_served_and_recovered(
        self, session_client, workspace, issue, create_user
    ):
        asset = attachment(workspace, issue, create_user)
        store(asset)

        response = session_client.get(attachments_url(workspace, issue, asset.id))

        assert response.status_code == status.HTTP_302_FOUND
        asset.refresh_from_db()
        assert asset.is_uploaded is True
        # From now on it is listed again
        listed = session_client.get(attachments_url(workspace, issue))
        assert [str(item["id"]) for item in listed.data] == [str(asset.id)]

    def test_a_file_that_never_arrived_says_so(self, session_client, workspace, issue, create_user):
        asset = attachment(workspace, issue, create_user)

        response = session_client.get(attachments_url(workspace, issue, asset.id))

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["code"] == "ASSET_NOT_UPLOADED"
        assert "Upload it again" in response.data["error"]

    def test_when_storage_cannot_be_asked_nothing_is_decided(self, session_client, workspace, issue, create_user):
        asset = attachment(workspace, issue, create_user)

        with mock.patch("plane.utils.asset_upload.find_stored_file", side_effect=StorageUnavailable("down")):
            response = session_client.get(attachments_url(workspace, issue, asset.id))

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["code"] == "STORAGE_UNAVAILABLE"
        asset.refresh_from_db()
        assert asset.is_uploaded is False

    def test_a_confirmed_file_is_served_without_asking_storage(self, session_client, workspace, issue, create_user):
        asset = attachment(workspace, issue, create_user, is_uploaded=True)

        with mock.patch("plane.utils.asset_upload.find_stored_file") as find:
            response = session_client.get(attachments_url(workspace, issue, asset.id))

        assert response.status_code == status.HTTP_302_FOUND
        find.assert_not_called()


@pytest.mark.contract
@pytest.mark.django_db
class TestListingAttachments:
    def test_the_work_item_shows_and_counts_only_finished_uploads(self, session_client, workspace, issue, create_user):
        done = attachment(workspace, issue, create_user, is_uploaded=True, name="done.pdf")
        attachment(workspace, issue, create_user, name="failed.pdf")
        url = f"/api/workspaces/{workspace.slug}/projects/{issue.project_id}/issues/{issue.id}/"

        response = session_client.get(url, {"expand": "issue_attachments"})

        assert response.status_code == status.HTTP_200_OK
        assert [str(item["id"]) for item in response.data["issue_attachments"]] == [str(done.id)]
        assert response.data["attachment_count"] == 1


@pytest.mark.contract
@pytest.mark.django_db
class TestAskingForAnUploadLink:
    def test_a_file_over_the_limit_is_refused_with_the_limit(self, session_client, workspace, issue):
        response = session_client.post(
            attachments_url(workspace, issue),
            {"name": "big.pdf", "type": "application/pdf", "size": settings.FILE_SIZE_LIMIT + 1},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "FILE_TOO_LARGE"
        assert response.data["limit"] == settings.FILE_SIZE_LIMIT
        assert not FileAsset.objects.filter(issue_id=issue.id).exists()

    def test_a_file_at_the_limit_gets_a_link(self, session_client, workspace, issue):
        response = session_client.post(
            attachments_url(workspace, issue),
            {"name": "big.pdf", "type": "application/pdf", "size": settings.FILE_SIZE_LIMIT},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

    def test_a_refused_type_says_why(self, session_client, workspace, issue):
        response = session_client.post(
            attachments_url(workspace, issue),
            {"name": "run.exe", "type": "application/x-msdownload", "size": 10},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "FILE_TYPE_NOT_ALLOWED"
