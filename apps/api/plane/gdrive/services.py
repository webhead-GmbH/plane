# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Linking projects to Drive folders, and putting a work item's files where they belong.

The layout in Drive is the team's existing one:

    <root>                      e.g. projects / webhead, chosen in settings
      <project folder>          one per project, linked or made by Plane
        Tasks                   made the first time a work item needs it
          WEB-42                one per work item, named after its id
            screenshot.png
"""

# Python imports
import json
import logging
import re
from contextlib import contextmanager

# Third party imports
from botocore.exceptions import BotoCoreError, ClientError

# Django imports
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

# Module imports
from plane.db.models import FileAsset, Issue
from plane.gdrive.client import FOLDER_MIME, DriveClient, DriveError
from plane.gdrive.matching import confident_match, folder_name_for, looks_taken, rank
from plane.gdrive.models import DriveConnection, DriveFile, DriveIssueFolder, DriveProjectFolder

logger = logging.getLogger(__name__)

TASKS_FOLDER = "Tasks"
# Pieces of a file moved from Plane's storage: a whole number of Google's 256 KiB units.
MOVE_CHUNK = 32 * 256 * 1024
# How long a move is taken to be running, at most, if its worker never says it ended.
MOVE_TIMEOUT = 6 * 3600


@contextmanager
def _lock(key, timeout=60):
    """One worker at a time per folder, so two uploads at once do not make it twice."""
    lock = cache.lock(f"gdrive:lock:{key}", timeout=timeout, blocking_timeout=timeout)
    acquired = lock.acquire()
    try:
        yield
    finally:
        if acquired:
            try:
                lock.release()
            except Exception:  # noqa: BLE001 — an expired lock is harmless here
                pass


def connection_for(workspace_id):
    """The workspace's connection, whatever state it is in."""
    return DriveConnection.objects.filter(workspace_id=workspace_id).first()


def ready_connection_for(workspace_id):
    connection = connection_for(workspace_id)
    return connection if connection and connection.is_ready else None


def root_folders(connection):
    """The project folders under the root, cached briefly: every settings row reads them."""
    key = f"gdrive:root-folders:{connection.id}:{connection.root_folder_id}"
    folders = cache.get(key)
    if folders is None:
        folders = DriveClient(connection).list_folders(connection.root_folder_id)
        cache.set(key, folders, 120)
    return folders


def forget_root_folders(connection):
    cache.delete(f"gdrive:root-folders:{connection.id}:{connection.root_folder_id}")


def suggestions_for(connection, project, limit=5):
    """The folders most like the project; "clear" marks the one linking suggested folders would pick."""
    folders = root_folders(connection)
    clear = confident_match(project.name, folders, project.identifier)
    return [
        {
            "id": folder["id"],
            "name": folder["name"],
            "score": value,
            "clear": bool(clear and clear["id"] == folder["id"]),
        }
        for folder, value in rank(project.name, folders, limit=limit, identifier=project.identifier)
    ]


def link_project(connection, project, folder_id, user=None, method=DriveProjectFolder.Method.CHOSEN):
    """Point a project at an existing folder."""
    meta = DriveClient(connection).get(folder_id, fields="id,name,mimeType,trashed")
    if meta.get("mimeType") != FOLDER_MIME or meta.get("trashed"):
        raise DriveError("That is not a folder Plane can use.", reason="not_a_folder")
    # all_objects: an unlinked project leaves a soft-deleted row, and the project
    # can only have one row, so it is brought back rather than added beside.
    link, _ = DriveProjectFolder.all_objects.update_or_create(
        project=project,
        defaults={
            "deleted_at": None,
            "workspace_id": project.workspace_id,
            "folder_id": meta["id"],
            "folder_name": meta.get("name", ""),
            # A different folder has a different "Tasks" folder in it, if any.
            "tasks_folder_id": "",
            "method": method,
            "updated_by": user,
        },
    )
    return link


def create_project_folder(connection, project, user=None):
    """Make the project's folder under the root, named the team's way ("209 - Name"), and link it."""
    with _lock(f"project:{project.id}"):
        existing = DriveProjectFolder.objects.filter(project=project).first()
        if existing:
            return existing
        name = folder_name_for(project.identifier, project.name)
        folder = DriveClient(connection).create_folder(connection.root_folder_id, name)
        forget_root_folders(connection)
        DriveProjectFolder.all_objects.filter(project=project).delete()
        return DriveProjectFolder.objects.create(
            workspace_id=project.workspace_id,
            project=project,
            folder_id=folder["id"],
            folder_name=folder.get("name", name),
            method=DriveProjectFolder.Method.CREATED,
            created_by=user,
        )


def link_new_project(project, user=None):
    """For a project just made: its existing folder if one clearly is, else a new one.

    Returns what was done: "matched", "created", "ambiguous" when folders carry its
    identifier or name but none clearly enough (two of them, or one named for
    another project's number) and a person has to say which, or "skipped" when the
    workspace has no ready connection or does not want this.
    """
    connection = ready_connection_for(project.workspace_id)
    if connection is None or not connection.auto_link_new_projects:
        return "skipped"
    if DriveProjectFolder.objects.filter(project=project).exists():
        return "skipped"
    forget_root_folders(connection)
    folders = root_folders(connection)
    match = confident_match(project.name, folders, project.identifier)
    if match:
        link_project(connection, project, match["id"], user, DriveProjectFolder.Method.MATCHED)
        return "matched"
    if looks_taken(project.name, folders, project.identifier):
        # Not another folder beside the ones that look like its own, and not a guess between them.
        return "ambiguous"
    create_project_folder(connection, project, user)
    return "created"


def _tasks_folder(client, link):
    if link.tasks_folder_id:
        return link.tasks_folder_id
    with _lock(f"tasks:{link.project_id}"):
        link.refresh_from_db(fields=["tasks_folder_id"])
        if not link.tasks_folder_id:
            folder = client.ensure_folder(link.folder_id, TASKS_FOLDER)
            link.tasks_folder_id = folder["id"]
            link.save(update_fields=["tasks_folder_id", "updated_at"])
    return link.tasks_folder_id


def issue_folder_name(issue):
    return f"{issue.project.identifier}-{issue.sequence_id}"


def ensure_issue_folder(connection, issue):
    """The work item's own folder inside "Tasks", made the first time something goes in it."""
    existing = DriveIssueFolder.objects.filter(issue=issue).first()
    if existing:
        return existing
    link = DriveProjectFolder.objects.filter(project_id=issue.project_id).first()
    if link is None:
        raise DriveError("This project has no Google Drive folder yet.", reason="project_not_linked")
    client = DriveClient(connection)
    tasks_id = _tasks_folder(client, link)
    with _lock(f"issue:{issue.id}"):
        existing = DriveIssueFolder.objects.filter(issue=issue).first()
        if existing:
            return existing
        name = issue_folder_name(issue)
        folder = client.ensure_folder(tasks_id, name)
        return DriveIssueFolder.objects.create(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue=issue,
            folder_id=folder["id"],
            folder_name=folder.get("name", name),
        )


def start_upload(connection, issue, user, name, size, mime_type, source, origin=None):
    """Record a file on its way to Drive and open the session its bytes go to."""
    folder = ensure_issue_folder(connection, issue)
    session = DriveClient(connection).start_upload(folder.folder_id, name, mime_type, size, origin)
    return DriveFile.objects.create(
        workspace_id=issue.workspace_id,
        project_id=issue.project_id,
        issue=issue,
        source=source,
        name=name,
        mime_type=mime_type or "application/octet-stream",
        size=size,
        upload_session_url=session,
        created_by=user,
    )


def finish_upload(drive_file, meta):
    """Mark a file as in Drive, from Google's own description of it."""
    drive_file.drive_file_id = meta["id"]
    drive_file.name = meta.get("name") or drive_file.name
    drive_file.mime_type = meta.get("mimeType") or drive_file.mime_type
    drive_file.size = int(meta.get("size") or drive_file.size)
    drive_file.web_view_link = meta.get("webViewLink", "")
    drive_file.state = DriveFile.State.UPLOADED
    drive_file.upload_session_url = ""
    drive_file.uploaded_at = timezone.now()
    drive_file.save()
    return drive_file


# ─── Attachments from before the folder ─────────────────────────────────────


def plane_attachments(workspace_id, issue_id=None):
    """Attachments still in Plane's own storage, on work items whose project has a Drive folder."""
    linked = DriveProjectFolder.objects.filter(workspace_id=workspace_id).values("project_id")
    attachments = FileAsset.objects.filter(
        workspace_id=workspace_id,
        entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
        is_uploaded=True,
        is_deleted=False,
        issue__isnull=False,
        issue__deleted_at__isnull=True,
        project_id__in=linked,
    )
    return attachments.filter(issue_id=issue_id) if issue_id else attachments


def moving_key(workspace_id, issue_id=None):
    """Set while a move runs: for one work item, or for the whole workspace."""
    return f"gdrive:moving:{workspace_id}:{issue_id or 'all'}"


def is_moving(workspace_id, issue_id=None):
    keys = [moving_key(workspace_id)] + ([moving_key(workspace_id, issue_id)] if issue_id else [])
    return any(cache.get(key) for key in keys)


def _read(stream, amount):
    """Up to ``amount`` bytes, fewer only at the end: a stream may hand them over in smaller pieces."""
    parts, left = [], amount
    while left > 0:
        part = stream.read(left)
        if not part:
            break
        parts.append(part)
        left -= len(part)
    return b"".join(parts)


def _forget_stored_file(asset, storage):
    """Remove Plane's copy of a file now in Drive, the way Plane's own delete does it, and free its space."""
    # In place: a save in a worker, with nobody signed in, would clear who uploaded it.
    FileAsset.objects.filter(pk=asset.pk).update(is_deleted=True, deleted_at=timezone.now())
    storage.delete_files([asset.asset.name])


def _copy_stored_file(connection, asset, storage, issue, source):
    """Copy one of Plane's stored files into the work item's Drive folder, and record it there.

    The bytes go from storage to Google piece by piece, so a file of any size moves
    without being held whole. Returns the file as recorded, or None for an empty
    one, which frees nothing and which Google takes no piece of.
    """
    folder = ensure_issue_folder(connection, issue)
    key = asset.asset.name
    stored = storage.s3_client.get_object(Bucket=storage.aws_storage_bucket_name, Key=key)
    size = int(stored["ContentLength"])
    if size == 0:
        return None
    name = asset.attributes.get("name") or key.rsplit("/", 1)[-1]
    mime_type = asset.attributes.get("type") or stored.get("ContentType") or "application/octet-stream"

    drive = DriveClient(connection)
    session = drive.start_upload(folder.folder_id, name, mime_type, size)
    body, buffer, start, meta = stored["Body"], b"", 0, None
    while meta is None:
        buffer += _read(body, MOVE_CHUNK - len(buffer))
        if not buffer:
            raise DriveError("The file in Plane's storage ended before Google had all of it.")
        finished, received, meta = drive.upload_chunk(session, buffer, start, size)
        if not finished:
            # Google may keep less than it was sent; the rest goes again with the next piece.
            buffer, start = buffer[received - start :], received

    drive_file = DriveFile.objects.create(
        workspace_id=asset.workspace_id,
        project_id=issue.project_id,
        issue=issue,
        source=source,
        name=name,
        mime_type=mime_type,
        size=size,
        moved_from=asset.id,
    )
    finish_upload(drive_file, meta)
    # Who added it and when, as before: listed in its old place, under its uploader. Set
    # afterwards, since a save in a worker, with nobody signed in, clears who made it.
    DriveFile.objects.filter(pk=drive_file.pk).update(created_at=asset.created_at, created_by_id=asset.created_by_id)
    return drive_file


def move_attachment_to_drive(connection, asset, storage):
    """Put one of Plane's own attachments in its work item's Drive folder, and free its space on the server.

    The stored object is deleted only once Google has the whole file.
    """
    issue = Issue.all_objects.select_related("project").get(pk=asset.issue_id)
    drive_file = _copy_stored_file(connection, asset, storage, issue, DriveFile.Source.ATTACHMENT)
    if drive_file:
        _forget_stored_file(asset, storage)
    return drive_file


def move_plane_attachments(workspace_id, issue_id=None):
    """Move every attachment still in Plane's storage to Drive; returns (moved, failed)."""
    from plane.settings.storage import S3Storage

    connection = ready_connection_for(workspace_id)
    if connection is None:
        return 0, 0
    storage = S3Storage()
    moved = failed = 0
    for asset in plane_attachments(workspace_id, issue_id).order_by("created_at").iterator():
        try:
            if move_attachment_to_drive(connection, asset, storage):
                moved += 1
        except (DriveError, ClientError, BotoCoreError) as error:
            failed += 1
            logger.warning("Could not move attachment %s to Google Drive: %s", asset.id, error)
    return moved, failed


# ─── Images in a new work item's description ────────────────────────────────

# An image Plane keeps itself is in the text by its asset id; one in Drive is "gdrive-<id>".
STORED_IMAGE = re.compile(
    r'<image-component\b[^>]*?\ssrc="([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"'
)
DESCRIPTION_ASSETS = (
    FileAsset.EntityTypeContext.ISSUE_DESCRIPTION,
    FileAsset.EntityTypeContext.DRAFT_ISSUE_DESCRIPTION,
)


def stored_images(html):
    """The asset ids of the images a description keeps in Plane's storage."""
    return set(STORED_IMAGE.findall(html or ""))


def in_drive_instead(html, moved):
    """The text with each moved image pointing at its copy in Drive; ``moved`` maps asset id to Drive file id."""
    for asset_id, file_id in moved.items():
        html = html.replace(f'src="{asset_id}"', f'src="gdrive-{file_id}"')
    return html


def move_description_images(issue_id):
    """Move the images a work item's description keeps in Plane's storage into its Drive folder.

    A work item's folder is named after its id, so the images put in its
    description while it was being created could only go to Plane's storage;
    they follow it into Drive once it exists. Returns how many moved, and how many
    are not uploaded yet, for the caller to come back for.
    """
    from plane.settings.storage import S3Storage

    issue = Issue.objects.select_related("project").filter(pk=issue_id).first()
    if issue is None or not DriveProjectFolder.objects.filter(project_id=issue.project_id).exists():
        return 0, 0
    connection = ready_connection_for(issue.workspace_id)
    wanted = stored_images(issue.description_html)
    if connection is None or not wanted:
        return 0, 0
    assets = FileAsset.objects.filter(
        Q(project_id__isnull=True) | Q(project_id=issue.project_id),
        pk__in=wanted,
        workspace_id=issue.workspace_id,
        entity_type__in=DESCRIPTION_ASSETS,
    )
    storage = S3Storage()
    moved, pending = {}, 0
    for asset in assets:
        if not asset.is_uploaded:
            pending += 1
            continue
        try:
            drive_file = _copy_stored_file(connection, asset, storage, issue, DriveFile.Source.DESCRIPTION)
        except (DriveError, ClientError, BotoCoreError) as error:
            logger.warning("Could not move image %s to Google Drive: %s", asset.id, error)
            continue
        if drive_file:
            moved[asset] = drive_file
    if not moved:
        return 0, pending

    ids = {str(asset.id): str(drive_file.id) for asset, drive_file in moved.items()}
    with transaction.atomic():
        # The text as it is now, which may have changed while the images moved.
        current = Issue.objects.select_for_update().get(pk=issue.pk)
        description_json = json.dumps(current.description_json)
        for asset_id, file_id in ids.items():
            description_json = description_json.replace(f'"{asset_id}"', f'"gdrive-{file_id}"')
        # In place, so nothing else a save does runs again; the binary copy would still show the old images.
        Issue.objects.filter(pk=issue.pk).update(
            description_html=in_drive_instead(current.description_html, ids),
            description_json=json.loads(description_json),
            description_binary=None,
        )
    for asset in moved:
        _forget_stored_file(asset, storage)
    return len(moved), pending
