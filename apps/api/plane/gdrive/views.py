# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Google Drive endpoints: the workspace's connection and project folders, and a work item's files."""

# Python imports
import logging
from urllib.parse import urlencode

# Django imports
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue, Project, ProjectMember, Workspace, WorkspaceMember
from plane.gdrive import client as google
from plane.gdrive.client import DriveClient, DriveError, folder_id_from
from plane.gdrive.matching import confident_match
from plane.gdrive.models import DriveConnection, DriveFile, DriveIssueFolder, DriveProjectFolder
from plane.gdrive.services import (
    connection_for,
    create_project_folder,
    finish_upload,
    forget_root_folders,
    link_project,
    ready_connection_for,
    root_folders,
    start_upload,
    suggestions_for,
)

logger = logging.getLogger(__name__)

STATE_SALT = "plane.gdrive.oauth"
STATE_MAX_AGE = 15 * 60
# Google wants every chunk but the last to be a multiple of 256 KiB.
CHUNK_UNIT = 256 * 1024
DIRECT_CHUNK = 64 * CHUNK_UNIT  # 16 MiB, straight from the browser to Google
PREVIEW_SIZES = (200, 400, 800, 1600)
# An image Google has no thumbnail for yet is shown from its own bytes up to this size.
PREVIEW_FALLBACK_LIMIT = 15 * 1024 * 1024


def _folder_url(folder_id):
    return f"https://drive.google.com/drive/folders/{folder_id}"


def _drive_error_response(error):
    """A Drive failure as an answer the screen can say something useful about."""
    code = {
        "not_connected": "DRIVE_NOT_CONNECTED",
        "invalid_grant": "DRIVE_ACCESS_REVOKED",
        "project_not_linked": "DRIVE_PROJECT_NOT_LINKED",
        "notFound": "DRIVE_NOT_FOUND",
        "not_a_folder": "DRIVE_NOT_A_FOLDER",
        "insufficientFilePermissions": "DRIVE_NO_PERMISSION",
        "storageQuotaExceeded": "DRIVE_STORAGE_FULL",
    }.get(error.reason, "DRIVE_ERROR")
    http = status.HTTP_404_NOT_FOUND if code == "DRIVE_NOT_FOUND" else status.HTTP_502_BAD_GATEWAY
    if code in ("DRIVE_NOT_CONNECTED", "DRIVE_PROJECT_NOT_LINKED", "DRIVE_NOT_A_FOLDER"):
        http = status.HTTP_409_CONFLICT
    return Response({"error": error.message, "code": code}, status=http)


def _redirect_uri(request):
    return request.build_absolute_uri(reverse("gdrive-oauth-callback"))


def _connection_payload(request, connection):
    return {
        "client_id": connection.client_id if connection else "",
        "has_client_secret": bool(connection and connection.client_secret_encrypted),
        "redirect_uri": _redirect_uri(request),
        "connected": bool(connection and connection.is_connected),
        "account_email": connection.account_email if connection else "",
        "connected_at": connection.connected_at if connection else None,
        "root_folder": (
            {
                "id": connection.root_folder_id,
                "name": connection.root_folder_name,
                "path": connection.root_folder_path,
                "url": _folder_url(connection.root_folder_id),
            }
            if connection and connection.root_folder_id
            else None
        ),
        "auto_link_new_projects": connection.auto_link_new_projects if connection else True,
    }


def _file_payload(drive_file, slug):
    return {
        "id": str(drive_file.id),
        "issue_id": str(drive_file.issue_id),
        "name": drive_file.name,
        "mime_type": drive_file.mime_type,
        "size": drive_file.size,
        "source": drive_file.source,
        "state": drive_file.state,
        "is_image": drive_file.is_image,
        "web_view_link": drive_file.web_view_link,
        "preview_path": f"/api/workspaces/{slug}/drive/files/{drive_file.id}/preview/" if drive_file.is_image else "",
        "created_by": str(drive_file.created_by_id) if drive_file.created_by_id else None,
        "created_at": drive_file.created_at,
        "uploaded_at": drive_file.uploaded_at,
    }


# ─── The workspace's connection ─────────────────────────────────────────────


class DriveConnectionEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        return Response(_connection_payload(request, connection_for(workspace.id)))

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def patch(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        connection, _ = DriveConnection.objects.get_or_create(workspace=workspace)
        data = request.data

        if "client_id" in data:
            new_id = str(data.get("client_id") or "").strip()
            if new_id != connection.client_id:
                # Tokens belong to the client that issued them.
                connection.client_id = new_id
                connection.set_refresh_token("")
                connection.account_email = ""
        if data.get("client_secret"):
            connection.set_client_secret(str(data["client_secret"]).strip())
        if "auto_link_new_projects" in data:
            connection.auto_link_new_projects = bool(data["auto_link_new_projects"])

        if "root_folder" in data:
            raw = str(data.get("root_folder") or "").strip()
            if not raw:
                connection.root_folder_id = connection.root_folder_name = connection.root_folder_path = ""
            else:
                folder_id = "root" if raw == "root" else folder_id_from(raw)
                if not folder_id:
                    return Response(
                        {"error": "That is not a Google Drive folder or folder link.", "code": "DRIVE_BAD_LINK"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    drive = DriveClient(connection)
                    meta = drive.get(folder_id, fields="id,name,mimeType,trashed")
                    if meta.get("mimeType") != google.FOLDER_MIME or meta.get("trashed"):
                        raise DriveError("That is not a folder Plane can use.", reason="not_a_folder")
                    path = drive.path_of(meta["id"])
                except DriveError as error:
                    return _drive_error_response(error)
                forget_root_folders(connection)
                connection.root_folder_id = meta["id"]
                connection.root_folder_name = meta.get("name", "")
                connection.root_folder_path = " / ".join(path)

        connection.updated_by = request.user
        connection.save()
        return Response(_connection_payload(request, connection))

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug):
        """Disconnect the account. Project links stay, so reconnecting picks up where it was."""
        connection = connection_for(Workspace.objects.get(slug=slug).id)
        if connection and connection.is_connected:
            google.revoke(connection.get_refresh_token())
            cache.delete(f"gdrive:access-token:{connection.id}")
            connection.set_refresh_token("")
            connection.account_email = ""
            connection.connected_at = None
            connection.save()
        return Response(_connection_payload(request, connection))


class DriveAuthorizeEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        connection = connection_for(workspace.id)
        if not connection or not connection.client_id or not connection.client_secret_encrypted:
            return Response(
                {"error": "Enter the client id and secret first.", "code": "DRIVE_CLIENT_MISSING"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        origin = request.headers.get("Origin", "")
        state = signing.dumps(
            {"w": str(workspace.id), "u": str(request.user.id), "o": origin, "s": slug}, salt=STATE_SALT
        )
        return Response({"url": google.authorization_url(connection.client_id, _redirect_uri(request), state)})


def _allowed_origin(origin):
    allowed = {getattr(settings, "WEB_URL", None), getattr(settings, "APP_BASE_URL", None)}
    allowed |= set(getattr(settings, "CORS_ALLOWED_ORIGINS", []) or [])
    allowed = {value.rstrip("/") for value in allowed if value}
    return origin.rstrip("/") if origin and origin.rstrip("/") in allowed else None


class DriveOAuthCallbackEndpoint(BaseAPIView):
    """Where Google sends the admin back. Trusts only the signed state it was handed."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            state = signing.loads(request.GET.get("state", ""), salt=STATE_SALT, max_age=STATE_MAX_AGE)
        except signing.BadSignature:
            return HttpResponse("This sign-in link is not valid any more. Start again from Plane.", status=400)

        base = _allowed_origin(state.get("o")) or (settings.WEB_URL or settings.APP_BASE_URL or "").rstrip("/")
        back = f"{base}/{state['s']}/settings/google-drive"

        def finish(outcome):
            return HttpResponseRedirect(f"{back}?{urlencode({'drive': outcome})}")

        if request.GET.get("error"):
            return finish("refused")
        connection = DriveConnection.objects.filter(workspace_id=state["w"]).first()
        if connection is None:
            return finish("failed")
        try:
            tokens = google.exchange_code(
                connection.client_id,
                connection.get_client_secret(),
                request.GET.get("code", ""),
                _redirect_uri(request),
            )
        except DriveError as error:
            logger.warning("Google Drive sign-in for workspace %s failed: %s", state["w"], error.message)
            return finish("failed")
        if not tokens.get("refresh_token"):
            return finish("no_refresh_token")

        connection.set_refresh_token(tokens["refresh_token"])
        cache.set(f"gdrive:access-token:{connection.id}", tokens["access_token"], 3000)
        try:
            user = DriveClient(connection).about().get("user", {})
            connection.account_email = user.get("emailAddress", "")
        except DriveError:
            connection.account_email = ""
        connection.connected_at = timezone.now()
        connection.connected_by_id = state.get("u")
        connection.save()
        return finish("connected")


class DriveFoldersEndpoint(BaseAPIView):
    """Folders to choose the project folder root from, one level at a time."""

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug):
        connection = connection_for(Workspace.objects.get(slug=slug).id)
        if not connection or not connection.is_connected:
            return _drive_error_response(DriveError("Google Drive is not connected.", reason="not_connected"))
        parent = request.GET.get("parent", "")
        drive = DriveClient(connection)
        try:
            if not parent:
                items = [
                    {"id": "root", "name": "My Drive", "kind": "my_drive"},
                    {"id": "shared-with-me", "name": "Shared with me", "kind": "shared_with_me"},
                ] + [{"id": item["id"], "name": item["name"], "kind": "shared_drive"} for item in drive.shared_drives()]
            elif parent == "shared-with-me":
                items = [
                    {"id": item["id"], "name": item["name"], "kind": "folder"}
                    for item in drive.shared_with_me_folders()
                ]
            else:
                items = [
                    {"id": item["id"], "name": item["name"], "kind": "folder"} for item in drive.list_folders(parent)
                ]
        except DriveError as error:
            return _drive_error_response(error)
        return Response({"items": items})


# ─── Project folders ────────────────────────────────────────────────────────


def _project_row(connection, project, link, folders_ready):
    return {
        "project": {"id": str(project.id), "name": project.name, "identifier": project.identifier},
        "folder": (
            {"id": link.folder_id, "name": link.folder_name, "url": _folder_url(link.folder_id), "method": link.method}
            if link
            else None
        ),
        "suggestions": suggestions_for(connection, project) if folders_ready and not link else [],
    }


class DriveProjectsEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        connection = connection_for(workspace.id)
        projects = Project.objects.filter(workspace=workspace, archived_at__isnull=True).order_by("name")
        links = {link.project_id: link for link in DriveProjectFolder.objects.filter(workspace=workspace)}
        folders, ready = [], bool(connection and connection.is_ready)
        if ready:
            try:
                folders = root_folders(connection)
            except DriveError as error:
                return _drive_error_response(error)
        return Response(
            {
                "folders": [{"id": item["id"], "name": item["name"]} for item in folders],
                "projects": [_project_row(connection, project, links.get(project.id), ready) for project in projects],
            }
        )


class DriveLinkSuggestedEndpoint(BaseAPIView):
    """Link every project that has no folder yet to the folder its name clearly matches."""

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        connection = ready_connection_for(workspace.id)
        if connection is None:
            return _drive_error_response(DriveError("Google Drive is not connected.", reason="not_connected"))
        linked_ids = set(DriveProjectFolder.objects.filter(workspace=workspace).values_list("project_id", flat=True))
        linked = 0
        try:
            folders = root_folders(connection)
            for project in Project.objects.filter(workspace=workspace, archived_at__isnull=True):
                if project.id in linked_ids:
                    continue
                match = confident_match(project.name, folders)
                if match:
                    link_project(connection, project, match["id"], request.user, DriveProjectFolder.Method.MATCHED)
                    linked += 1
        except DriveError as error:
            return _drive_error_response(error)
        return Response({"linked": linked})


class DriveProjectFolderEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def put(self, request, slug, project_id):
        workspace = Workspace.objects.get(slug=slug)
        connection = ready_connection_for(workspace.id)
        if connection is None:
            return _drive_error_response(DriveError("Google Drive is not connected.", reason="not_connected"))
        project = Project.objects.filter(workspace=workspace, pk=project_id).first()
        if project is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            if request.data.get("create"):
                DriveProjectFolder.all_objects.filter(project=project).delete()
                link = create_project_folder(connection, project, request.user)
            else:
                folder_id = folder_id_from(str(request.data.get("folder_id") or ""))
                if not folder_id:
                    return Response(
                        {"error": "Choose a folder.", "code": "DRIVE_BAD_LINK"}, status=status.HTTP_400_BAD_REQUEST
                    )
                link = link_project(connection, project, folder_id, request.user)
        except DriveError as error:
            return _drive_error_response(error)
        return Response(_project_row(connection, project, link, False))

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, project_id):
        # A real delete: the project can have one link, and a soft-deleted one would block the next.
        DriveProjectFolder.all_objects.filter(workspace__slug=slug, project_id=project_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── A work item's files ────────────────────────────────────────────────────


def _issue(slug, project_id, issue_id):
    return (
        Issue.issue_objects.filter(workspace__slug=slug, project_id=project_id, pk=issue_id)
        .select_related("project")
        .first()
    )


class DriveIssueEndpoint(BaseAPIView):
    """Whether a work item's files go to Drive, and the ones attached to it."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, issue_id):
        workspace = Workspace.objects.get(slug=slug)
        connection = ready_connection_for(workspace.id)
        link = DriveProjectFolder.objects.filter(project_id=project_id).first()
        folder = DriveIssueFolder.objects.filter(issue_id=issue_id).first()
        files = DriveFile.objects.filter(
            issue_id=issue_id, project_id=project_id, state=DriveFile.State.UPLOADED, source=DriveFile.Source.ATTACHMENT
        )
        return Response(
            {
                "enabled": bool(connection and link),
                "folder_url": _folder_url(folder.folder_id)
                if folder
                else (_folder_url(link.folder_id) if link else ""),
                "files": [_file_payload(item, slug) for item in files],
            }
        )


class DriveUploadEndpoint(BaseAPIView):
    """Open an upload: the file is recorded, and the browser is given where to send its bytes."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def post(self, request, slug, project_id, issue_id):
        issue = _issue(slug, project_id, issue_id)
        if issue is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        connection = ready_connection_for(issue.workspace_id)
        if connection is None:
            return _drive_error_response(DriveError("Google Drive is not connected.", reason="not_connected"))

        name = str(request.data.get("name") or "").strip()[:1024]
        try:
            size = int(request.data.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        source = request.data.get("source") or DriveFile.Source.ATTACHMENT
        if not name or size <= 0 or source not in DriveFile.Source.values:
            return Response(
                {"error": "A file needs a name and a size.", "code": "DRIVE_BAD_FILE"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            drive_file = start_upload(
                connection,
                issue,
                request.user,
                name,
                size,
                str(request.data.get("mime_type") or ""),
                source,
                origin=request.headers.get("Origin"),
            )
        except DriveError as error:
            return _drive_error_response(error)
        return Response(
            {
                "file": _file_payload(drive_file, slug),
                "upload_url": drive_file.upload_session_url,
                "chunk_size": DIRECT_CHUNK,
                "relay_chunk_size": _relay_chunk(),
            },
            status=status.HTTP_201_CREATED,
        )


def _relay_chunk():
    """The largest chunk the server will take in one request, in whole 256 KiB units."""
    limit = min(settings.DATA_UPLOAD_MAX_MEMORY_SIZE or (4 * 1024 * 1024), 16 * CHUNK_UNIT)
    return max((limit // CHUNK_UNIT) * CHUNK_UNIT, CHUNK_UNIT)


class DriveUploadDetailEndpoint(BaseAPIView):
    """How far an upload has got, and the server's route for the bytes where the direct one fails."""

    def _own_upload(self, request, slug, project_id, issue_id, upload_id):
        return DriveFile.objects.filter(
            pk=upload_id, workspace__slug=slug, project_id=project_id, issue_id=issue_id, created_by=request.user
        ).first()

    def _answer(self, drive_file, slug, finished, received, meta):
        if finished:
            finish_upload(drive_file, meta)
            return Response({"done": True, "file": _file_payload(drive_file, slug)})
        return Response({"done": False, "received": received or 0})

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, issue_id, upload_id):
        drive_file = self._own_upload(request, slug, project_id, issue_id, upload_id)
        if drive_file is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if drive_file.state == DriveFile.State.UPLOADED:
            return Response({"done": True, "file": _file_payload(drive_file, slug)})
        connection = connection_for(drive_file.workspace_id)
        try:
            finished, received, meta = DriveClient(connection).upload_status(
                drive_file.upload_session_url, drive_file.size
            )
        except DriveError as error:
            return _drive_error_response(error)
        return self._answer(drive_file, slug, finished, received, meta)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def put(self, request, slug, project_id, issue_id, upload_id):
        drive_file = self._own_upload(request, slug, project_id, issue_id, upload_id)
        if drive_file is None or drive_file.state == DriveFile.State.UPLOADED:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        # Where these bytes start, in the address: a Content-Range header would need
        # its own CORS allowance whenever the web app and the API are on two origins.
        offset = request.GET.get("offset", "")
        if not offset.isdigit() or int(offset) >= drive_file.size or not request.body:
            return Response(
                {"error": "Say which bytes these are.", "code": "DRIVE_BAD_RANGE"}, status=status.HTTP_400_BAD_REQUEST
            )
        connection = connection_for(drive_file.workspace_id)
        try:
            finished, received, meta = DriveClient(connection).upload_chunk(
                drive_file.upload_session_url, request.body, int(offset), drive_file.size
            )
        except DriveError as error:
            return _drive_error_response(error)
        return self._answer(drive_file, slug, finished, received, meta)


class DriveFileEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def delete(self, request, slug, project_id, issue_id, file_id):
        """Take an attachment off the work item and put the file in Drive's bin, where it can be got back."""
        drive_file = DriveFile.objects.filter(
            pk=file_id, workspace__slug=slug, project_id=project_id, issue_id=issue_id
        ).first()
        if drive_file is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        is_admin = ProjectMember.objects.filter(
            project_id=project_id, member=request.user, role=ROLE.ADMIN.value, is_active=True
        ).exists()
        if drive_file.created_by_id != request.user.id and not is_admin:
            return Response(
                {"error": "Only the person who added it, or a project admin, can remove it."},
                status=status.HTTP_403_FORBIDDEN,
            )
        connection = connection_for(drive_file.workspace_id)
        if drive_file.drive_file_id and connection and connection.is_connected:
            try:
                DriveClient(connection).trash(drive_file.drive_file_id)
            except DriveError as error:
                if error.reason != "notFound":
                    return _drive_error_response(error)
        drive_file.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _viewable_file(request, slug, file_id):
    """A file in Drive that this person may see: they are on its project, or run the workspace."""
    drive_file = DriveFile.objects.filter(pk=file_id, workspace__slug=slug, state=DriveFile.State.UPLOADED).first()
    if drive_file is None:
        return None
    on_project = ProjectMember.objects.filter(
        project_id=drive_file.project_id, member=request.user, is_active=True
    ).exists()
    is_workspace_admin = WorkspaceMember.objects.filter(
        workspace__slug=slug, member=request.user, role=ROLE.ADMIN.value, is_active=True
    ).exists()
    return drive_file if on_project or is_workspace_admin else None


class DriveFileOpenEndpoint(BaseAPIView):
    """Where a file in Drive opens, for a link in the text that points at it by its Plane id."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, file_id):
        drive_file = _viewable_file(request, slug, file_id)
        if drive_file is None or not drive_file.web_view_link:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return HttpResponseRedirect(drive_file.web_view_link)


class DriveFilePreviewEndpoint(BaseAPIView):
    """An image in Drive as something an <img> can show, for anyone on the file's project."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, file_id):
        drive_file = _viewable_file(request, slug, file_id)
        if drive_file is None or not drive_file.is_image:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            wanted = int(request.GET.get("size", 800))
        except ValueError:
            wanted = 800
        size = min(PREVIEW_SIZES, key=lambda candidate: abs(candidate - wanted))
        key = f"gdrive:preview:{drive_file.drive_file_id}:{size}"
        cached = cache.get(key)
        if cached is None:
            connection = connection_for(drive_file.workspace_id)
            if not connection or not connection.is_connected:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            drive = DriveClient(connection)
            try:
                cached = drive.thumbnail(drive_file.drive_file_id, size)
                if cached is None and drive_file.size <= PREVIEW_FALLBACK_LIMIT:
                    # Google makes thumbnails a little after the upload; until then, the image itself.
                    original = drive.content(drive_file.drive_file_id)
                    cached = (original.content, drive_file.mime_type)
                    cache.set(key, cached, 60)
                elif cached is not None:
                    cache.set(key, cached, 6 * 3600)
            except DriveError as error:
                return _drive_error_response(error)
        if cached is None:
            return Response({"error": "No preview yet."}, status=status.HTTP_404_NOT_FOUND)
        body, content_type = cached
        response = HttpResponse(body, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        return response
