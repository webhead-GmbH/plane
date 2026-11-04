# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The Google Drive endpoints, with Google itself replaced by a small in-memory Drive."""

# Python imports
import io
from unittest import mock
from uuid import uuid4

# Third-party imports
import pytest
from django.core import signing
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import FileAsset, Issue, IssueComment, State
from plane.gdrive.client import FOLDER_MIME, DriveError
from plane.gdrive.models import DriveConnection, DriveFile, DriveIssueFolder, DriveProjectFolder
from plane.gdrive.references import follow_text
from plane.gdrive.services import link_new_project, move_description_images
from plane.gdrive.tasks import move_plane_attachments_to_drive
from plane.tests.factories import (
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    WorkspaceFactory,
    WorkspaceMemberFactory,
)

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

ROOT = "root-folder-id"


class FakeDrive:
    """Enough of Drive to follow what Plane asks of it."""

    def __init__(self):
        self.items = {ROOT: {"id": ROOT, "name": "webhead", "mimeType": FOLDER_MIME, "parents": []}}
        self.sessions = {}
        self.trashed = []
        self.untrashed = []

    def add_folder(self, name, parent=ROOT):
        folder_id = f"folder-id-{len(self.items):04d}"
        self.items[folder_id] = {"id": folder_id, "name": name, "mimeType": FOLDER_MIME, "parents": [parent]}
        return folder_id

    def children(self, parent):
        return [item for item in self.items.values() if parent in item["parents"] and item["mimeType"] == FOLDER_MIME]

    # The DriveClient surface Plane uses.
    def get(self, file_id, fields=None):
        if file_id not in self.items:
            raise DriveError("File not found.", 404, "notFound")
        return {**self.items[file_id], "trashed": False}

    def list_folders(self, parent):
        return [{"id": item["id"], "name": item["name"]} for item in self.children(parent)]

    def path_of(self, folder_id):
        return ["My Drive", "projects", self.items[folder_id]["name"]]

    def find_folder(self, parent, name):
        return next(({"id": i["id"], "name": i["name"]} for i in self.children(parent) if i["name"] == name), None)

    def create_folder(self, parent, name):
        return {"id": self.add_folder(name, parent), "name": name}

    def ensure_folder(self, parent, name):
        return self.find_folder(parent, name) or self.create_folder(parent, name)

    def start_upload(self, parent, name, mime_type, size, origin=None):
        url = f"https://upload.example/session/{len(self.sessions)}"
        self.sessions[url] = {
            "parent": parent,
            "name": name,
            "mime": mime_type,
            "size": size,
            "got": 0,
            "origin": origin,
        }
        return url

    def _answer(self, session):
        if session["got"] >= session["size"]:
            file_id = f"file-id-{len(self.items):04d}"
            self.items[file_id] = {
                "id": file_id,
                "name": session["name"],
                "mimeType": session["mime"],
                "parents": [session["parent"]],
                "size": str(session["size"]),
                "webViewLink": f"https://drive.google.com/file/d/{file_id}/view",
            }
            return True, None, self.items[file_id]
        return False, session["got"], None

    def upload_status(self, url, size):
        return self._answer(self.sessions[url])

    def upload_chunk(self, url, data, start, total):
        session = self.sessions[url]
        session["got"] = start + len(data)
        return self._answer(session)

    def trash(self, file_id):
        self.trashed.append(file_id)

    def untrash(self, file_id):
        self.untrashed.append(file_id)


@pytest.fixture
def drive():
    fake = FakeDrive()
    with (
        mock.patch("plane.gdrive.views.DriveClient", return_value=fake),
        mock.patch("plane.gdrive.services.DriveClient", return_value=fake),
        mock.patch("plane.gdrive.references.DriveClient", return_value=fake),
        mock.patch("plane.gdrive.services._lock"),
    ):
        yield fake


@pytest.fixture
def setup():
    admin = UserFactory(username=uuid4().hex)
    workspace = WorkspaceFactory(owner=admin)
    WorkspaceMemberFactory(workspace=workspace, member=admin, role=ROLE.ADMIN.value)
    member = UserFactory(username=uuid4().hex)
    WorkspaceMemberFactory(workspace=workspace, member=member, role=ROLE.MEMBER.value)
    project = ProjectFactory(workspace=workspace, name="Fisch Gruber", identifier="FISCH", created_by=admin)
    ProjectMemberFactory(project=project, member=admin, role=ROLE.ADMIN.value)
    ProjectMemberFactory(project=project, member=member, role=ROLE.MEMBER.value)
    state = State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted")
    issue = Issue.objects.create(project=project, workspace=workspace, name="Logo", state=state)
    connection = DriveConnection(
        workspace=workspace, client_id="client", root_folder_id=ROOT, root_folder_name="webhead"
    )
    connection.set_client_secret("secret")
    connection.set_refresh_token("refresh")
    connection.save()
    return {"admin": admin, "member": member, "workspace": workspace, "project": project, "issue": issue}


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def issue_url(setup, tail=""):
    s = setup
    return f"/api/workspaces/{s['workspace'].slug}/projects/{s['project'].id}/issues/{s['issue'].id}/drive/{tail}"


class TestConnection:
    def test_the_secret_and_token_are_never_sent_back(self, setup):
        body = client_for(setup["admin"]).get(f"/api/workspaces/{setup['workspace'].slug}/drive/connection/").json()
        assert body["connected"] is True
        assert body["has_client_secret"] is True
        assert "secret" not in str(body).replace("has_client_secret", "")
        assert body["redirect_uri"].endswith("/api/gdrive/oauth/callback/")

    def test_only_an_admin_can_see_or_change_it(self, setup):
        url = f"/api/workspaces/{setup['workspace'].slug}/drive/connection/"
        assert client_for(setup["member"]).get(url).status_code == 403
        assert client_for(setup["member"]).patch(url, {"client_id": "x"}, format="json").status_code == 403

    def test_a_pasted_folder_link_becomes_the_root(self, setup, drive):
        folder = drive.add_folder("projects")
        response = client_for(setup["admin"]).patch(
            f"/api/workspaces/{setup['workspace'].slug}/drive/connection/",
            {"root_folder": f"https://drive.google.com/drive/folders/{folder}?usp=sharing"},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["root_folder"]["id"] == folder
        assert response.json()["root_folder"]["path"] == "My Drive / projects / projects"

    def test_changing_the_client_drops_the_old_token(self, setup):
        client_for(setup["admin"]).patch(
            f"/api/workspaces/{setup['workspace'].slug}/drive/connection/", {"client_id": "other"}, format="json"
        )
        assert not DriveConnection.objects.get(workspace=setup["workspace"]).is_connected

    def test_the_callback_refuses_a_forged_state(self, setup):
        response = APIClient().get("/api/gdrive/oauth/callback/?state=forged&code=x")
        assert response.status_code == 400

    def test_the_callback_stores_the_refresh_token(self, setup, drive):
        DriveConnection.objects.filter(workspace=setup["workspace"]).update(refresh_token_encrypted="")
        state = signing.dumps(
            {"w": str(setup["workspace"].id), "u": str(setup["admin"].id), "o": "", "s": setup["workspace"].slug},
            salt="plane.gdrive.oauth",
        )
        with (
            mock.patch(
                "plane.gdrive.views.google.exchange_code",
                return_value={"refresh_token": "new-refresh", "access_token": "a"},
            ),
            mock.patch.object(
                FakeDrive, "about", create=True, return_value={"user": {"emailAddress": "it@example.com"}}
            ),
        ):
            response = APIClient().get(f"/api/gdrive/oauth/callback/?state={state}&code=abc")
        assert response.status_code == 302
        assert response["Location"].endswith(f"/{setup['workspace'].slug}/settings/google-drive?drive=connected")
        connection = DriveConnection.objects.get(workspace=setup["workspace"])
        assert connection.get_refresh_token() == "new-refresh"
        assert connection.account_email == "it@example.com"


class TestProjectFolders:
    def test_projects_come_with_folder_suggestions(self, setup, drive):
        drive.add_folder("fisch-gruber")
        drive.add_folder("Huber")
        body = client_for(setup["admin"]).get(f"/api/workspaces/{setup['workspace'].slug}/drive/projects/").json()
        row = next(row for row in body["projects"] if row["project"]["id"] == str(setup["project"].id))
        assert row["folder"] is None
        assert row["suggestions"][0]["name"] == "fisch-gruber"
        assert row["suggestions"][0]["clear"] is True
        assert all(not suggestion["clear"] for suggestion in row["suggestions"][1:])
        assert {folder["name"] for folder in body["folders"]} == {"fisch-gruber", "Huber"}

    def test_link_suggested_links_clear_matches_only(self, setup, drive):
        drive.add_folder("fisch-gruber")
        response = client_for(setup["admin"]).post(
            f"/api/workspaces/{setup['workspace'].slug}/drive/projects/link-suggested/"
        )
        assert response.json() == {"linked": 1}
        assert DriveProjectFolder.objects.get(project=setup["project"]).method == "matched"

    def test_a_folder_can_be_chosen_or_made(self, setup, drive):
        folder = drive.add_folder("Anything")
        url = f"/api/workspaces/{setup['workspace'].slug}/drive/projects/{setup['project'].id}/folder/"
        admin = client_for(setup["admin"])
        assert admin.put(url, {"folder_id": folder}, format="json").json()["folder"]["id"] == folder
        made = admin.put(url, {"create": True}, format="json").json()["folder"]
        assert drive.items[made["id"]]["name"] == "FISCH - Fisch Gruber"
        assert admin.delete(url).status_code == 204
        assert not DriveProjectFolder.objects.filter(project=setup["project"]).exists()

    def test_a_new_project_takes_its_matching_folder(self, setup, drive):
        drive.add_folder("Neues Projekt")
        project = ProjectFactory(workspace=setup["workspace"], name="Neues  projekt", identifier="NEU")
        assert link_new_project(project) == "matched"
        assert DriveProjectFolder.objects.get(project=project).folder_name == "Neues Projekt"

    def test_a_new_project_with_no_match_gets_a_new_folder(self, setup, drive):
        project = ProjectFactory(workspace=setup["workspace"], name="Ganz Neu", identifier="GANZ")
        assert link_new_project(project) == "created"
        assert drive.find_folder(ROOT, "GANZ - Ganz Neu") is not None

    def test_a_new_project_with_two_folders_of_its_name_is_left_to_a_person(self, setup, drive):
        drive.add_folder("Neues Projekt")
        drive.add_folder("Neues Projekt GmbH")
        project = ProjectFactory(workspace=setup["workspace"], name="Neues Projekt", identifier="NEU")
        assert link_new_project(project) == "ambiguous"
        assert not DriveProjectFolder.objects.filter(project=project).exists()
        assert len([item for item in drive.items.values() if item["name"].startswith("Neues Projekt")]) == 2

    def test_a_folder_named_with_the_projects_number_is_found_and_offered_to_create(self, setup, drive):
        project = ProjectFactory(workspace=setup["workspace"], name="Alias Immo", identifier="288")
        drive.add_folder("288 - Alias")
        drive.add_folder("Alias Immo Archiv")
        body = client_for(setup["admin"]).get(f"/api/workspaces/{setup['workspace'].slug}/drive/projects/").json()
        row = next(row for row in body["projects"] if row["project"]["id"] == str(project.id))
        assert row["project"]["new_folder_name"] == "288 - Alias Immo"
        assert (row["suggestions"][0]["name"], row["suggestions"][0]["clear"]) == ("288 - Alias", True)

    def test_a_new_project_takes_the_folder_with_its_number(self, setup, drive):
        drive.add_folder("209 - ATTN-SEEKR Webseite")
        project = ProjectFactory(workspace=setup["workspace"], name="ATTN–SEEKR Webseite", identifier="209")
        assert link_new_project(project) == "matched"
        assert DriveProjectFolder.objects.get(project=project).folder_name == "209 - ATTN-SEEKR Webseite"

    def test_a_new_project_beside_a_folder_with_another_number_is_left_to_a_person(self, setup, drive):
        drive.add_folder("290 - Biohof Radl")
        project = ProjectFactory(workspace=setup["workspace"], name="Biohof Radl", identifier="284")
        assert link_new_project(project) == "ambiguous"
        assert not DriveProjectFolder.objects.filter(project=project).exists()
        assert drive.find_folder(ROOT, "284 - Biohof Radl") is None

    def test_nothing_is_made_when_the_workspace_does_not_want_it(self, setup, drive):
        DriveConnection.objects.filter(workspace=setup["workspace"]).update(auto_link_new_projects=False)
        project = ProjectFactory(workspace=setup["workspace"], name="Ohne", identifier="OHNE")
        assert link_new_project(project) == "skipped"


@pytest.fixture
def linked(setup, drive):
    folder = drive.add_folder("Fisch Gruber")
    DriveProjectFolder.objects.create(
        workspace=setup["workspace"], project=setup["project"], folder_id=folder, folder_name="Fisch Gruber"
    )
    return folder


class TestUploads:
    def test_without_a_project_folder_drive_is_off_for_the_work_item(self, setup, drive):
        assert client_for(setup["member"]).get(issue_url(setup)).json()["enabled"] is False

    def test_an_upload_goes_into_tasks_and_the_work_items_folder(self, setup, drive, linked):
        member = client_for(setup["member"])
        response = member.post(
            issue_url(setup, "uploads/"),
            {"name": "brief.pdf", "size": 10, "mime_type": "application/pdf"},
            format="json",
            HTTP_ORIGIN="http://localhost:3100",
        )
        assert response.status_code == 201
        body = response.json()
        session = drive.sessions[body["upload_url"]]
        assert session["origin"] == "http://localhost:3100"
        issue_folder = drive.items[session["parent"]]
        assert issue_folder["name"] == "FISCH-1"
        assert drive.items[issue_folder["parents"][0]]["name"] == "Tasks"
        assert body["relay_chunk_size"] % (256 * 1024) == 0

        # The bytes arrive (here through the server's relay), and the file is recorded.
        detail = issue_url(setup, f"uploads/{body['file']['id']}/")
        answer = member.put(f"{detail}?offset=0", data=b"0123456789", content_type="application/octet-stream").json()
        assert answer["done"] is True
        assert answer["file"]["web_view_link"].startswith("https://drive.google.com/file/d/")
        assert client_for(setup["admin"]).get(issue_url(setup)).json()["files"][0]["name"] == "brief.pdf"

    def test_a_second_upload_reuses_the_folders(self, setup, drive, linked):
        member = client_for(setup["member"])
        for name in ("a.txt", "b.txt"):
            member.post(issue_url(setup, "uploads/"), {"name": name, "size": 3}, format="json")
        assert DriveIssueFolder.objects.filter(issue=setup["issue"]).count() == 1
        assert len([item for item in drive.items.values() if item["name"] == "Tasks"]) == 1

    def test_finishing_a_direct_upload_asks_google_not_the_browser(self, setup, drive, linked):
        member = client_for(setup["member"])
        body = member.post(issue_url(setup, "uploads/"), {"name": "big.zip", "size": 5}, format="json").json()
        detail = issue_url(setup, f"uploads/{body['file']['id']}/")
        assert member.get(detail).json() == {"done": False, "received": 0}
        drive.sessions[body["upload_url"]]["got"] = 5  # the browser sent it straight to Google
        assert member.get(detail).json()["done"] is True

    def test_a_relayed_piece_must_say_where_it_starts(self, setup, drive, linked):
        member = client_for(setup["member"])
        body = member.post(issue_url(setup, "uploads/"), {"name": "x.txt", "size": 4}, format="json").json()
        detail = issue_url(setup, f"uploads/{body['file']['id']}/")
        for tail in ("", "?offset=-1", "?offset=4", "?offset=abc"):
            response = member.put(f"{detail}{tail}", data=b"abcd", content_type="application/octet-stream")
            assert response.status_code == 400, tail
            assert response.json()["code"] == "DRIVE_BAD_RANGE"

    def test_somebody_else_cannot_use_your_upload(self, setup, drive, linked):
        body = (
            client_for(setup["member"])
            .post(issue_url(setup, "uploads/"), {"name": "x.txt", "size": 1}, format="json")
            .json()
        )
        response = client_for(setup["admin"]).get(issue_url(setup, f"uploads/{body['file']['id']}/"))
        assert response.status_code == 404

    def test_there_is_no_size_or_type_limit(self, setup, drive, linked):
        response = client_for(setup["member"]).post(
            issue_url(setup, "uploads/"),
            {"name": "footage.mov", "size": 40 * 1024**3, "mime_type": "video/quicktime"},
            format="json",
        )
        assert response.status_code == 201

    def test_removing_puts_the_file_in_drives_bin(self, setup, drive, linked):
        member = client_for(setup["member"])
        body = member.post(issue_url(setup, "uploads/"), {"name": "x.txt", "size": 1}, format="json").json()
        member.put(
            issue_url(setup, f"uploads/{body['file']['id']}/?offset=0"),
            data=b"x",
            content_type="application/octet-stream",
        )
        drive_id = DriveFile.objects.get(pk=body["file"]["id"]).drive_file_id
        assert member.delete(issue_url(setup, f"files/{body['file']['id']}/")).status_code == 204
        assert drive.trashed == [drive_id]
        assert not DriveFile.objects.filter(pk=body["file"]["id"]).exists()

    def test_only_the_uploader_or_an_admin_can_remove(self, setup, drive, linked):
        body = (
            client_for(setup["admin"])
            .post(issue_url(setup, "uploads/"), {"name": "x.txt", "size": 1}, format="json")
            .json()
        )
        response = client_for(setup["member"]).delete(issue_url(setup, f"files/{body['file']['id']}/"))
        assert response.status_code == 403

    def test_a_link_in_the_text_opens_the_file_for_people_on_the_project(self, setup, drive, linked):
        member = client_for(setup["member"])
        body = member.post(issue_url(setup, "uploads/"), {"name": "x.txt", "size": 1}, format="json").json()
        member.put(
            issue_url(setup, f"uploads/{body['file']['id']}/?offset=0"),
            data=b"x",
            content_type="application/octet-stream",
        )
        url = f"/api/workspaces/{setup['workspace'].slug}/drive/files/{body['file']['id']}/open/"
        response = member.get(url)
        assert response.status_code == 302
        assert response["Location"] == DriveFile.objects.get(pk=body["file"]["id"]).web_view_link

        outsider = UserFactory(username=uuid4().hex)
        WorkspaceMemberFactory(workspace=setup["workspace"], member=outsider, role=ROLE.MEMBER.value)
        assert client_for(outsider).get(url).status_code == 404


def in_drive(setup, source, name="brief.pdf"):
    """A file that has arrived in the work item's Drive folder."""
    google_id = f"g-{uuid4().hex[:12]}"
    return DriveFile.objects.create(
        workspace=setup["workspace"],
        project=setup["project"],
        issue=setup["issue"],
        source=source,
        state=DriveFile.State.UPLOADED,
        name=name,
        size=1,
        drive_file_id=google_id,
        web_view_link=f"https://drive.google.com/file/d/{google_id}/view?usp=drivesdk",
    )


def link_to(drive_file):
    return f'<p><a href="{drive_file.web_view_link}" target="_blank">{drive_file.name}</a></p>'


def image_of(drive_file):
    return f'<image-component src="gdrive-{drive_file.id}" status="uploaded"></image-component>'


class TestFilesInText:
    @pytest.fixture(autouse=True)
    def follow_now(self):
        """The task the text hands its files to, run on the spot."""
        with mock.patch("plane.gdrive.tasks.follow_text_files.delay", side_effect=follow_text):
            yield

    def comment(self, setup, html, capture):
        with capture(execute=True):
            made = IssueComment.objects.create(
                workspace=setup["workspace"],
                project=setup["project"],
                issue=setup["issue"],
                actor=setup["member"],
                comment_html=html,
            )
        return made

    def edit_description(self, setup, html, capture):
        with capture(execute=True):
            issue = Issue.objects.get(pk=setup["issue"].pk)
            issue.description_html = html
            issue.save()

    def test_a_file_taken_out_of_a_comment_goes_to_the_bin(
        self, setup, drive, linked, django_capture_on_commit_callbacks
    ):
        drive_file = in_drive(setup, DriveFile.Source.COMMENT)
        made = self.comment(setup, link_to(drive_file), django_capture_on_commit_callbacks)
        with django_capture_on_commit_callbacks(execute=True):
            comment = IssueComment.objects.get(pk=made.pk)
            comment.comment_html = "<p>No file after all</p>"
            comment.save()
        assert drive.trashed == [drive_file.drive_file_id]
        assert not DriveFile.objects.filter(pk=drive_file.pk).exists()

    def test_deleting_a_comment_bins_its_files(self, setup, drive, linked, django_capture_on_commit_callbacks):
        image = in_drive(setup, DriveFile.Source.COMMENT, "logo.png")
        made = self.comment(setup, image_of(image), django_capture_on_commit_callbacks)
        with django_capture_on_commit_callbacks(execute=True):
            IssueComment.objects.get(pk=made.pk).delete()
        assert drive.trashed == [image.drive_file_id]

    def test_a_file_still_mentioned_elsewhere_stays(self, setup, drive, linked, django_capture_on_commit_callbacks):
        drive_file = in_drive(setup, DriveFile.Source.COMMENT)
        made = self.comment(setup, link_to(drive_file), django_capture_on_commit_callbacks)
        self.edit_description(setup, link_to(drive_file), django_capture_on_commit_callbacks)
        with django_capture_on_commit_callbacks(execute=True):
            IssueComment.objects.get(pk=made.pk).delete()
        assert drive.trashed == []
        assert DriveFile.objects.filter(pk=drive_file.pk).exists()

    def test_an_image_back_in_the_description_comes_out_of_the_bin(
        self, setup, drive, linked, django_capture_on_commit_callbacks
    ):
        image = in_drive(setup, DriveFile.Source.DESCRIPTION, "logo.png")
        self.edit_description(setup, image_of(image), django_capture_on_commit_callbacks)
        self.edit_description(setup, "<p></p>", django_capture_on_commit_callbacks)
        assert drive.trashed == [image.drive_file_id]
        # An undo, or an older version restored.
        self.edit_description(setup, image_of(image), django_capture_on_commit_callbacks)
        assert drive.untrashed == [image.drive_file_id]
        assert DriveFile.objects.filter(pk=image.pk).exists()

    def test_attachments_are_left_alone(self, setup, drive, linked, django_capture_on_commit_callbacks):
        attachment = in_drive(setup, DriveFile.Source.ATTACHMENT)
        self.edit_description(setup, link_to(attachment), django_capture_on_commit_callbacks)
        self.edit_description(setup, "<p></p>", django_capture_on_commit_callbacks)
        assert drive.trashed == []


class FakeStorage:
    """Plane's own storage, holding a few objects."""

    aws_storage_bucket_name = "uploads"

    def __init__(self):
        self.objects = {}
        self.deleted = []
        self.s3_client = self

    def get_object(self, Bucket, Key):
        data = self.objects[Key]
        return {"ContentLength": len(data), "ContentType": "application/pdf", "Body": io.BytesIO(data)}

    def delete_files(self, names):
        self.deleted.extend(names)
        return True


class TestMovingPlaneAttachments:
    @pytest.fixture
    def storage(self):
        fake = FakeStorage()
        # The move runs in a worker, after the request and with nobody signed in: queued here
        # and run by post(), outside the request, the way the worker would.
        fake.queued = []
        with (
            mock.patch("plane.settings.storage.S3Storage", return_value=fake),
            mock.patch(
                "plane.gdrive.tasks.move_plane_attachments_to_drive.delay",
                side_effect=lambda *args: fake.queued.append(args),
            ),
        ):
            yield fake

    def post(self, client, url, storage):
        response = client.post(url)
        while storage.queued:
            move_plane_attachments_to_drive(*storage.queued.pop(0))
        return response

    def stored(self, setup, storage, name="report.pdf", data=b"0123456789", project=None, issue=None):
        key = f"{setup['workspace'].id}/{uuid4().hex}-{name}"
        storage.objects[key] = data
        asset = FileAsset.objects.create(
            asset=key,
            attributes={"name": name, "type": "application/pdf", "size": len(data)},
            size=len(data),
            entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
            is_uploaded=True,
            workspace=setup["workspace"],
            project=project or setup["project"],
            issue=issue or setup["issue"],
        )
        # Uploaded by the member: set after the save, which clears it with nobody signed in.
        FileAsset.objects.filter(pk=asset.pk).update(created_by=setup["member"])
        asset.refresh_from_db()
        return asset

    def test_a_work_items_attachments_move_to_its_folder(self, setup, drive, linked, storage):
        asset = self.stored(setup, storage)
        with mock.patch("plane.gdrive.services.MOVE_CHUNK", 4):
            response = self.post(client_for(setup["member"]), issue_url(setup, "move-plane-files/"), storage)
        assert response.status_code == 202

        body = client_for(setup["member"]).get(issue_url(setup)).json()
        assert [item["name"] for item in body["files"]] == ["report.pdf"]
        assert body["moving"] is False
        moved = DriveFile.objects.get(issue=setup["issue"])
        assert drive.items[moved.drive_file_id]["size"] == "10"
        assert drive.items[drive.items[moved.drive_file_id]["parents"][0]]["name"] == "FISCH-1"
        assert moved.created_by_id == setup["member"].id
        # Off the Plane server: the record removed the way Plane removes it, the bytes deleted.
        asset.refresh_from_db()
        assert asset.is_deleted is True
        assert storage.deleted == [asset.asset.name]

    def test_a_piece_google_only_partly_kept_is_sent_again(self, setup, drive, linked, storage):
        self.stored(setup, storage, data=b"abcdefghij")
        received = {}

        def keep_three(url, data, start, total):
            session = drive.sessions[url]
            assert start == session["got"], "the move must carry on from what Google has"
            kept = data if start + len(data) == total else data[:3]
            received[url] = received.get(url, b"") + kept
            session["got"] = start + len(kept)
            return drive._answer(session)

        with mock.patch("plane.gdrive.services.MOVE_CHUNK", 4), mock.patch.object(drive, "upload_chunk", keep_three):
            self.post(client_for(setup["member"]), issue_url(setup, "move-plane-files/"), storage)
        assert list(received.values()) == [b"abcdefghij"]

    def test_the_workspace_count_covers_linked_projects_only(self, setup, drive, linked, storage):
        other = ProjectFactory(workspace=setup["workspace"], name="Elsewhere", identifier="ELSE")
        state = State.objects.create(name="Todo", project=other, workspace=setup["workspace"], group="unstarted")
        elsewhere = Issue.objects.create(project=other, workspace=setup["workspace"], name="Other", state=state)
        self.stored(setup, storage, data=b"12345")
        self.stored(setup, storage, data=b"123", project=other, issue=elsewhere)
        url = f"/api/workspaces/{setup['workspace'].slug}/drive/plane-files/"

        assert client_for(setup["member"]).get(url).status_code == 403
        admin = client_for(setup["admin"])
        assert admin.get(url).json() == {"count": 1, "size": 5, "moving": False}
        assert self.post(admin, url, storage).status_code == 202
        assert admin.get(url).json() == {"count": 0, "size": 0, "moving": False}
        assert FileAsset.objects.filter(issue=elsewhere, is_deleted=False).count() == 1

    def test_a_project_without_a_folder_cannot_move_anything(self, setup, drive, storage):
        self.stored(setup, storage)
        response = self.post(client_for(setup["member"]), issue_url(setup, "move-plane-files/"), storage)
        assert response.status_code == 409


class TestImagesOfNewWorkItems:
    """Images put in the description while a work item was being made follow it into Drive."""

    @pytest.fixture
    def storage(self):
        fake = FakeStorage()
        fake.queued = []
        with (
            mock.patch("plane.settings.storage.S3Storage", return_value=fake),
            mock.patch(
                "plane.gdrive.tasks.move_new_issue_images.apply_async",
                side_effect=lambda args, countdown=None: fake.queued.append(args),
            ),
        ):
            yield fake

    def image(self, setup, storage, uploaded=True):
        key = f"{setup['workspace'].id}/{uuid4().hex}-logo.png"
        storage.objects[key] = b"\x89PNG-bytes"
        asset = FileAsset.objects.create(
            asset=key,
            attributes={"name": "logo.png", "type": "image/png", "size": 10},
            size=10,
            entity_type=FileAsset.EntityTypeContext.ISSUE_DESCRIPTION,
            is_uploaded=uploaded,
            workspace=setup["workspace"],
            project=setup["project"],
        )
        FileAsset.objects.filter(pk=asset.pk).update(created_by=setup["member"])
        asset.refresh_from_db()
        return asset

    def make_issue(self, setup, html, capture):
        with capture(execute=True):
            return Issue.objects.create(
                project=setup["project"],
                workspace=setup["workspace"],
                name="New logo",
                state=setup["issue"].state,
                description_html=html,
            )

    @staticmethod
    def html_with(asset):
        return f'<p>Logo:</p><image-component src="{asset.id}" status="uploaded"></image-component>'

    def test_they_move_once_the_work_item_exists(
        self, setup, drive, linked, storage, django_capture_on_commit_callbacks
    ):
        asset = self.image(setup, storage)
        issue = self.make_issue(setup, self.html_with(asset), django_capture_on_commit_callbacks)
        assert storage.queued == [[str(issue.id)]]
        assert move_description_images(issue.id) == (1, 0)

        moved = DriveFile.objects.get(issue=issue)
        assert moved.source == DriveFile.Source.DESCRIPTION
        assert moved.moved_from == asset.id
        assert moved.created_by_id == setup["member"].id
        assert drive.items[drive.items[moved.drive_file_id]["parents"][0]]["name"] == "FISCH-2"
        issue.refresh_from_db()
        assert f'src="gdrive-{moved.id}"' in issue.description_html
        assert str(asset.id) not in issue.description_html
        assert storage.deleted == [asset.asset.name]
        assert FileAsset.all_objects.get(pk=asset.pk).is_deleted is True

    def test_an_editor_opened_before_the_move_saves_them_in_drive(
        self, setup, drive, linked, storage, django_capture_on_commit_callbacks
    ):
        asset = self.image(setup, storage)
        stale = self.html_with(asset)
        issue = self.make_issue(setup, stale, django_capture_on_commit_callbacks)
        move_description_images(issue.id)
        moved = DriveFile.objects.get(issue=issue)

        issue = Issue.objects.get(pk=issue.pk)
        issue.description_html = stale + "<p>typed later</p>"
        issue.save()
        issue.refresh_from_db()
        assert f'src="gdrive-{moved.id}"' in issue.description_html
        assert "typed later" in issue.description_html
        # Still in the text, so not sent to the bin.
        assert drive.trashed == []

    def test_an_image_still_uploading_is_left_for_later(
        self, setup, drive, linked, storage, django_capture_on_commit_callbacks
    ):
        asset = self.image(setup, storage, uploaded=False)
        issue = self.make_issue(setup, self.html_with(asset), django_capture_on_commit_callbacks)
        assert move_description_images(issue.id) == (0, 1)
        assert not DriveFile.objects.filter(issue=issue).exists()

    def test_a_project_without_a_folder_keeps_them(self, setup, drive, storage, django_capture_on_commit_callbacks):
        asset = self.image(setup, storage)
        issue = self.make_issue(setup, self.html_with(asset), django_capture_on_commit_callbacks)
        assert move_description_images(issue.id) == (0, 0)
        issue.refresh_from_db()
        assert str(asset.id) in issue.description_html
