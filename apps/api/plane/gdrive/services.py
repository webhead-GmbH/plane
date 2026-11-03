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
import logging
from contextlib import contextmanager

# Django imports
from django.core.cache import cache
from django.utils import timezone

# Module imports
from plane.gdrive.client import FOLDER_MIME, DriveClient, DriveError
from plane.gdrive.matching import confident_match, rank, same_name
from plane.gdrive.models import DriveConnection, DriveFile, DriveIssueFolder, DriveProjectFolder

logger = logging.getLogger(__name__)

TASKS_FOLDER = "Tasks"


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
    """The folders most like the project's name; "clear" marks the one linking suggested folders would pick."""
    folders = root_folders(connection)
    clear = confident_match(project.name, folders)
    return [
        {
            "id": folder["id"],
            "name": folder["name"],
            "score": value,
            "clear": bool(clear and clear["id"] == folder["id"]),
        }
        for folder, value in rank(project.name, folders, limit=limit)
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
    """Make a folder named after the project under the root, and link it."""
    with _lock(f"project:{project.id}"):
        existing = DriveProjectFolder.objects.filter(project=project).first()
        if existing:
            return existing
        folder = DriveClient(connection).create_folder(connection.root_folder_id, project.name.strip())
        forget_root_folders(connection)
        DriveProjectFolder.all_objects.filter(project=project).delete()
        return DriveProjectFolder.objects.create(
            workspace_id=project.workspace_id,
            project=project,
            folder_id=folder["id"],
            folder_name=folder.get("name", project.name),
            method=DriveProjectFolder.Method.CREATED,
            created_by=user,
        )


def link_new_project(project, user=None):
    """For a project just made: its existing folder if the name clearly matches one, else a new one.

    Returns what was done: "matched", "created", "ambiguous" when two folders carry
    its name and a person has to say which, or "skipped" when the workspace has no
    ready connection or does not want this.
    """
    connection = ready_connection_for(project.workspace_id)
    if connection is None or not connection.auto_link_new_projects:
        return "skipped"
    if DriveProjectFolder.objects.filter(project=project).exists():
        return "skipped"
    forget_root_folders(connection)
    folders = root_folders(connection)
    match = confident_match(project.name, folders)
    if match:
        link_project(connection, project, match["id"], user, DriveProjectFolder.Method.MATCHED)
        return "matched"
    if any(same_name(project.name, folder["name"]) for folder in folders):
        # Not a third folder with the name, and not a guess between the two.
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
