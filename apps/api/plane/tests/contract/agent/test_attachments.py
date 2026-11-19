# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Attaching a file to a work item through a connected app.

Storage is faked throughout, both Plane's own and Google Drive's: what is being checked is
what the app is allowed to send, where it ends up, and that nothing is stored twice or in the
wrong place. Nothing here reaches a real Drive.
"""

# Python imports
import uuid
from unittest import mock

# Third-party imports
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

# Module imports
from plane.agent.models import AgentIdempotencyKey
from plane.app.permissions import ROLE
from plane.db.models import FileAsset
from plane.gdrive.client import DriveError
from plane.gdrive.models import DriveFile
from plane.tests.contract.agent.conftest import client_with
from plane.tests.contract.agent.world import join, make_issue, make_project, make_user, make_workspace

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

MEMBER, GUEST = ROLE.MEMBER.value, ROLE.GUEST.value
WRITE = "profile work_items:read work_items:write"


@pytest.fixture
def workspace(person):
    workspace = make_workspace()
    join(workspace, person)
    return workspace


@pytest.fixture
def project(workspace, person):
    return make_project(workspace, "PRJ", members=[(person, MEMBER)])


@pytest.fixture
def issue(project):
    return make_issue(project, "Task")


@pytest.fixture
def client(app, person):
    return client_with(app, person, WRITE)


@pytest.fixture
def plane_storage(monkeypatch):
    """Plane's own file storage, recording what it was given."""
    from plane.agent.services import files

    storage = mock.MagicMock()
    storage.upload_file.return_value = True
    monkeypatch.setattr(files, "S3Storage", mock.MagicMock(return_value=storage))
    monkeypatch.setattr(files, "ready_connection_for", lambda workspace_id: None)
    return storage


def url(workspace, ref="PRJ-1"):
    return f"/api/agent/v1/workspaces/{workspace.slug}/work-items/{ref}/attachments/"


def send(
    client, workspace, content=b"hello", name="notes.txt", content_type="text/plain", ref="PRJ-1", key="auto", **extra
):
    headers = {} if key is None else {"HTTP_IDEMPOTENCY_KEY": ("key-" + uuid.uuid4().hex) if key == "auto" else key}
    file = SimpleUploadedFile(name, content, content_type=content_type)
    return client.post(url(workspace, ref), {"file": file, **extra}, format="multipart", **headers)


class TestPlaneStorage:
    def test_a_file_is_stored_as_the_person_and_the_activity_feed_is_told(
        self, client, workspace, issue, person, plane_storage, background_tasks
    ):
        response = send(client, workspace, b"%PDF-1.4 fake", "report.pdf", "application/pdf")
        assert response.status_code == 201, response.content
        body = response.json()
        assert body["work_item"] == "PRJ-1" and body["url"].endswith("/PRJ-1/")
        assert body["file"] == {
            "id": mock.ANY,
            "name": "report.pdf",
            "type": "application/pdf",
            "size": 13,
            "storage": "plane",
            "link": None,
        }
        asset = FileAsset.objects.get()
        assert asset.is_uploaded and asset.created_by == person and asset.issue_id == issue.id
        assert asset.entity_type == FileAsset.EntityTypeContext.ISSUE_ATTACHMENT
        key, content_type = plane_storage.upload_file.call_args.args[1:3]
        assert key == asset.asset.name and content_type == "application/pdf"
        assert background_tasks.issue_activity.call_args.kwargs["type"] == "attachment.activity.created"
        background_tasks.asset_metadata.assert_called_once()

    def test_a_name_with_a_path_in_it_is_reduced_to_the_name(self, client, workspace, issue, plane_storage):
        send(client, workspace, b"x", "../../etc/passwd.txt")
        asset = FileAsset.objects.get()
        assert asset.attributes["name"] == "passwd.txt"
        assert ".." not in asset.asset.name and asset.asset.name.endswith("-passwd.txt")

    def test_a_type_that_is_not_declared_is_read_from_the_name(self, client, workspace, issue, plane_storage):
        response = send(client, workspace, b"# hi", "readme.md", "")
        assert response.status_code == 201 and response.json()["file"]["type"] == "text/markdown"

    def test_storage_failing_leaves_nothing_behind(self, client, workspace, issue, plane_storage):
        plane_storage.upload_file.return_value = False
        response = send(client, workspace)
        assert response.status_code == 502 and response.json()["error"] == "storage_unavailable"
        assert not FileAsset.objects.exists() and not AgentIdempotencyKey.objects.exists()

    @pytest.mark.parametrize("error", ["unreachable", "refused"])
    def test_a_storage_server_that_cannot_be_reached_is_a_clean_failure_not_a_crash(
        self, client, workspace, issue, plane_storage, error
    ):
        from botocore.exceptions import ClientError, EndpointConnectionError

        plane_storage.upload_file.side_effect = (
            EndpointConnectionError(endpoint_url="http://minio.localhost:9000")
            if error == "unreachable"
            else ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "PutObject")
        )
        response = send(client, workspace)
        assert response.status_code == 502 and response.json()["error"] == "storage_unavailable"
        assert not FileAsset.objects.exists() and not AgentIdempotencyKey.objects.exists()

    def test_sending_it_again_with_the_same_key_stores_it_once(self, client, workspace, issue, plane_storage):
        first = send(client, workspace, b"same bytes", key="upload-key-0001")
        again = send(client, workspace, b"same bytes", key="upload-key-0001")
        assert first.status_code == again.status_code == 201 and again.json() == first.json()
        assert again["Idempotent-Replay"] == "true"
        assert FileAsset.objects.count() == 1 and plane_storage.upload_file.call_count == 1

    def test_the_same_key_for_a_different_file_is_refused(self, client, workspace, issue, plane_storage):
        send(client, workspace, b"one", key="upload-key-0002")
        other = send(client, workspace, b"two", key="upload-key-0002")
        assert other.status_code == 422 and other.json()["error"] == "idempotency_key_reused"
        assert FileAsset.objects.count() == 1

    def test_a_key_is_required(self, client, workspace, issue, plane_storage):
        assert send(client, workspace, key=None).status_code == 400
        assert not FileAsset.objects.exists()


class TestWhatMayBeSent:
    def test_exactly_one_file_in_the_field_called_file(self, client, workspace, issue, plane_storage):
        assert client.post(url(workspace), {}, format="multipart", HTTP_IDEMPOTENCY_KEY=("k" * 12)).status_code == 400
        misnamed = client.post(
            url(workspace),
            {"upload": SimpleUploadedFile("a.txt", b"x", content_type="text/plain")},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY=("k" * 12),
        )
        assert misnamed.status_code == 400
        assert not FileAsset.objects.exists()

    def test_other_form_fields_are_refused(self, client, workspace, issue, plane_storage):
        assert send(client, workspace, entity_type="avatar").status_code == 400
        assert not FileAsset.objects.exists()

    def test_an_empty_file_is_refused(self, client, workspace, issue, plane_storage):
        assert send(client, workspace, b"").status_code == 400

    def test_a_file_over_the_limit_is_refused_with_the_limit(self, client, workspace, issue, plane_storage, settings):
        settings.FILE_SIZE_LIMIT = 10
        response = send(client, workspace, b"x" * 11)
        assert response.status_code == 413 and response.json()["error"] == "file_too_large"
        assert response.json()["limit"] == 10
        assert not FileAsset.objects.exists()

    @pytest.mark.parametrize(
        ("name", "content_type"),
        [
            ("virus.exe", "application/x-msdownload"),
            ("script.sh", "application/x-sh"),
            ("page.html", "text/html"),
            ("noextension", ""),
            ("drawing.svg", "image/svg+xml"),
            ("sneaky.png", "image/svg+xml"),
        ],
    )
    def test_types_that_are_not_allowed_or_can_carry_scripts_are_refused(
        self, client, workspace, issue, plane_storage, name, content_type
    ):
        response = send(client, workspace, b"data", name, content_type)
        assert response.status_code == 400 and response.json()["error"] == "file_type_not_allowed"
        assert not FileAsset.objects.exists() and not plane_storage.upload_file.called

    def test_json_is_not_a_way_to_upload(self, client, workspace, issue, plane_storage):
        response = client.post(url(workspace), {"file": "abc"}, format="json", HTTP_IDEMPOTENCY_KEY=("k" * 12))
        assert response.status_code == 415


class TestWhoMayAttach:
    def test_the_write_scope_is_needed(self, app, person, workspace, issue, plane_storage):
        reader = client_with(app, person, "profile work_items:read")
        response = send(reader, workspace)
        assert response.status_code == 403 and response.json()["scope"] == "work_items:write"

    def test_a_guest_cannot(self, app, workspace, plane_storage):
        guest = make_user()
        join(workspace, guest)
        shared = make_project(workspace, "GST", members=[(guest, GUEST)])
        make_issue(shared, "Mine", author=guest)
        assert send(client_with(app, guest, WRITE), workspace, ref="GST-1").status_code == 403

    def test_work_that_cannot_be_seen_looks_like_work_that_is_not_there(self, client, workspace, plane_storage):
        private = make_project(workspace, "SEC", members=[])
        make_issue(private, "Salaries")
        hidden = send(client, workspace, ref="SEC-1")
        absent = send(client, workspace, ref="SEC-9")
        assert hidden.status_code == absent.status_code == 404 and hidden.json() == absent.json()
        assert not FileAsset.objects.exists()


class TestGoogleDrive:
    @pytest.fixture
    def drive(self, monkeypatch):
        """A workspace with Drive set up, and a Drive that records what it receives."""
        from plane.agent.services import files

        received = []

        class FakeDrive:
            def __init__(self, connection):
                pass

            def upload_chunk(self, session_url, data, start, total):
                received.append((start, len(data), total))
                last = start + len(data) >= total
                return (
                    last,
                    None if last else start + len(data),
                    (
                        {
                            "id": "drive-1",
                            "name": "n",
                            "size": str(total),
                            "mimeType": "text/plain",
                            "webViewLink": "https://drive.example/f/1",
                        }
                        if last
                        else None
                    ),
                )

        def fake_start(connection, issue, user, name, size, mime_type, source, origin=None):
            return DriveFile.objects.create(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                issue=issue,
                source=source,
                name=name,
                mime_type=mime_type,
                size=size,
                upload_session_url="https://upload.example/session",
                created_by=user,
            )

        monkeypatch.setattr(files, "ready_connection_for", lambda workspace_id: object())
        monkeypatch.setattr(files, "start_upload", fake_start)
        monkeypatch.setattr(files, "DriveClient", FakeDrive)
        monkeypatch.setattr(files, "S3Storage", mock.MagicMock(side_effect=AssertionError("Plane storage was used")))
        return received

    def test_when_drive_is_set_up_the_file_goes_there_and_not_to_plane_storage(
        self, client, workspace, issue, person, drive
    ):
        response = send(client, workspace, b"hello drive", "notes.txt")
        assert response.status_code == 201, response.content
        stored = response.json()["file"]
        assert stored["storage"] == "google_drive" and stored["link"] == "https://drive.example/f/1"
        file = DriveFile.objects.get()
        assert file.state == DriveFile.State.UPLOADED and file.drive_file_id == "drive-1" and file.created_by == person
        assert file.source == DriveFile.Source.ATTACHMENT
        assert not FileAsset.objects.exists()

    def test_a_big_file_is_sent_in_whole_pieces_in_order(self, client, workspace, issue, drive, monkeypatch):
        from plane.agent.services import files

        monkeypatch.setattr(files, "UPLOAD_CHUNK", 256 * 1024)
        data = b"x" * (600 * 1024)
        assert send(client, workspace, data, "big.txt").status_code == 201
        assert drive == [(0, 262144, len(data)), (262144, 262144, len(data)), (524288, 90112, len(data))]

    def test_drive_failing_leaves_no_half_made_file(self, client, workspace, issue, monkeypatch, drive):
        from plane.agent.services import files

        class Broken:
            def __init__(self, connection):
                pass

            def upload_chunk(self, *args):
                raise DriveError("quota exceeded")

        monkeypatch.setattr(files, "DriveClient", Broken)
        response = send(client, workspace)
        assert response.status_code == 502 and response.json()["error"] == "storage_unavailable"
        assert "quota exceeded" in response.json()["error_description"]
        assert not DriveFile.objects.exists() and not AgentIdempotencyKey.objects.exists()
