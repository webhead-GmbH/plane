# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Attaching a file to a work item on a person's behalf.

A chat app has the file's bytes and nothing else: no browser to hand an upload address to.
So here the app sends the file to Plane, and Plane puts it where the web app would have: in
the workspace's Google Drive folder for the work item when Drive is set up for the workspace
(the team's own layout), otherwise in Plane's file storage.

The checks are the web app's: a size limit, an allow-list of file types, a file name with
no path in it. One thing is stricter. SVG images can carry scripts, and a file a language
model or a chat user hands over is not something to serve from Plane's own address, so they
are refused here even though the web app takes them.
"""

# Python imports
import hashlib
import io
import json
import uuid

# Third-party imports
from botocore.exceptions import BotoCoreError, ClientError

# Django imports
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

# Module imports
from plane.agent.errors import AgentError, invalid_request
from plane.api.serializers import IssueAttachmentSerializer
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.storage_metadata_task import get_asset_object_metadata
from plane.db.models import FileAsset
from plane.gdrive.client import DriveClient, DriveError
from plane.gdrive.models import DriveFile
from plane.gdrive.services import MOVE_CHUNK, finish_upload, ready_connection_for, start_upload
from plane.settings.storage import S3Storage, StorageUnavailable
from plane.utils.attachment_type import attachment_type
from plane.utils.exception_logger import log_exception
from plane.utils.host import base_host
from plane.utils.path_validator import sanitize_filename

# Never accepted from a connected app, whatever the general allow-list says.
REFUSED_TYPES = frozenset({"image/svg+xml"})
# Pieces sent to Drive: a whole number of Google's 256 KiB units.
UPLOAD_CHUNK = MOVE_CHUNK


def read_upload(request):
    """The one file in the request, checked. Returns `(name, type, bytes)`."""
    files = request.FILES
    if len(files) != 1 or "file" not in files or len(files.getlist("file")) != 1:
        raise invalid_request("Send exactly one file, in a multipart field named 'file'.")
    extra = sorted(request.POST)
    if extra:
        raise invalid_request(f"Unknown field(s): {', '.join(extra)}. Send only the file.")

    upload = files["file"]
    name = sanitize_filename(upload.name)
    if not name:
        raise invalid_request("The file needs a name.")
    if upload.size <= 0:
        raise invalid_request("The file is empty.")
    if upload.size > settings.FILE_SIZE_LIMIT:
        raise AgentError(
            "file_too_large",
            f"Files can be at most {settings.FILE_SIZE_LIMIT / (1024 * 1024):g} MB.",
            status_code=413,
            extra={"limit": settings.FILE_SIZE_LIMIT},
        )

    kind = attachment_type(name, upload.content_type or None)
    if not kind or kind not in settings.ATTACHMENT_MIME_TYPES or kind in REFUSED_TYPES:
        raise AgentError("file_type_not_allowed", "This type of file cannot be attached.", extra={"type": kind})
    return name, kind, upload.read()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def attach(request, user, issue, name, kind, data):
    """Put the file where this workspace keeps work item files, and tell the activity feed."""
    connection = ready_connection_for(issue.workspace_id)
    if connection is not None:
        return _to_drive(connection, user, issue, name, kind, data)
    return _to_plane(request, user, issue, name, kind, data)


def _to_drive(connection, user, issue, name, kind, data):
    drive_file = None
    try:
        drive_file = start_upload(connection, issue, user, name, len(data), kind, DriveFile.Source.ATTACHMENT)
        client = DriveClient(connection)
        offset, finished, meta = 0, False, None
        while offset < len(data):
            piece = data[offset : offset + UPLOAD_CHUNK]
            finished, _received, meta = client.upload_chunk(drive_file.upload_session_url, piece, offset, len(data))
            offset += len(piece)
        if not finished:
            raise DriveError("Google Drive did not finish the upload.")
        finish_upload(drive_file, meta)
    except DriveError as error:
        if drive_file is not None:
            drive_file.delete()
        raise AgentError(
            "storage_unavailable", f"The file could not be saved to Google Drive: {error}", status_code=502
        )
    return {
        "id": str(drive_file.id),
        "name": drive_file.name,
        "type": drive_file.mime_type,
        "size": drive_file.size,
        "storage": "google_drive",
        "link": drive_file.web_view_link or None,
    }


def _to_plane(request, user, issue, name, kind, data):
    workspace = issue.workspace
    key = f"{workspace.id}/{uuid.uuid4().hex}-{name}"
    asset = FileAsset.objects.create(
        attributes={"name": name, "type": kind, "size": len(data)},
        asset=key,
        size=len(data),
        workspace_id=workspace.id,
        created_by=user,
        issue_id=issue.id,
        project_id=issue.project_id,
        entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
    )
    try:
        stored = S3Storage(request=request).upload_file(io.BytesIO(data), key, kind)
    except (BotoCoreError, ClientError, StorageUnavailable, OSError) as error:
        # The storage helper only catches the server's own refusals; a server that cannot be
        # reached at all comes out here, and must not leave a half-made attachment behind.
        log_exception(error)
        stored = False
    if not stored:
        asset.delete(soft=False)
        raise AgentError("storage_unavailable", "The file could not be saved.", status_code=502)

    asset.is_uploaded = True
    asset.save()
    issue_activity.delay(
        type="attachment.activity.created",
        requested_data=None,
        actor_id=str(user.id),
        issue_id=str(issue.id),
        project_id=str(issue.project_id),
        current_instance=json.dumps(IssueAttachmentSerializer(asset).data, cls=DjangoJSONEncoder),
        epoch=int(timezone.now().timestamp()),
        notification=True,
        origin=base_host(request=request, is_app=True),
    )
    get_asset_object_metadata.delay(str(asset.id))
    return {
        "id": str(asset.id),
        "name": name,
        "type": kind,
        "size": len(data),
        "storage": "plane",
        "link": None,
    }
