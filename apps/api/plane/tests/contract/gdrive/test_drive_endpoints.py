# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The Google Drive endpoints, with Google itself replaced by a small in-memory Drive."""

# Python imports
from unittest import mock
from uuid import uuid4

# Third-party imports
import pytest
from django.core import signing
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import Issue, State
from plane.gdrive.client import FOLDER_MIME, DriveError
from plane.gdrive.models import DriveConnection, DriveFile, DriveIssueFolder, DriveProjectFolder
from plane.gdrive.services import link_new_project
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


@pytest.fixture
def drive():
    fake = FakeDrive()
    with (
        mock.patch("plane.gdrive.views.DriveClient", return_value=fake),
        mock.patch("plane.gdrive.services.DriveClient", return_value=fake),
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
        assert drive.items[made["id"]]["name"] == "Fisch Gruber"
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
        assert drive.find_folder(ROOT, "Ganz Neu") is not None

    def test_a_new_project_with_two_folders_of_its_name_is_left_to_a_person(self, setup, drive):
        drive.add_folder("Neues Projekt")
        drive.add_folder("Neues Projekt GmbH")
        project = ProjectFactory(workspace=setup["workspace"], name="Neues Projekt", identifier="NEU")
        assert link_new_project(project) == "ambiguous"
        assert not DriveProjectFolder.objects.filter(project=project).exists()
        assert len([item for item in drive.items.values() if item["name"].startswith("Neues Projekt")]) == 2

    def test_nothing_is_made_when_the_workspace_does_not_want_it(self, setup, drive):
        DriveConnection.objects.filter(workspace=setup["workspace"]).update(auto_link_new_projects=False)
        project = ProjectFactory(workspace=setup["workspace"], name="Ohne", identifier="OHNE")
        assert link_new_project(project) == "skipped"


class TestUploads:
    @pytest.fixture
    def linked(self, setup, drive):
        folder = drive.add_folder("Fisch Gruber")
        DriveProjectFolder.objects.create(
            workspace=setup["workspace"], project=setup["project"], folder_id=folder, folder_name="Fisch Gruber"
        )
        return folder

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
