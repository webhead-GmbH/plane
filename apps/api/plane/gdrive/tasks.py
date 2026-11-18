# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import logging

# Third party imports
from celery import shared_task

# Django imports
from django.core.cache import cache

# Module imports
from plane.db.models import Project, User
from plane.gdrive.client import DriveError
from plane.gdrive.references import follow_text
from plane.gdrive.services import (
    link_new_project,
    move_description_images,
    move_plane_attachments,
    moving_key,
    ready_connection_for,
    rename_folders_for_identifier,
)

logger = logging.getLogger(__name__)


@shared_task
def link_new_project_folder(project_id, user_id=None):
    """Link a new project to the folder its name clearly matches, or make it one."""
    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return
    user = User.objects.filter(pk=user_id).first() if user_id else None
    try:
        outcome = link_new_project(project, user)
    except DriveError as error:
        logger.warning("Could not give project %s a Google Drive folder: %s", project_id, error.message)
        return
    if outcome != "skipped":
        logger.info("Project %s: Google Drive folder %s.", project_id, outcome)


@shared_task(bind=True, max_retries=3)
def rename_folders_for_new_identifier(self, project_id, old_identifier):
    """Rename the project's Drive folders to carry its new Project ID; the files stay where they are."""
    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return
    connection = ready_connection_for(project.workspace_id)
    if connection is None:
        return
    try:
        renamed = rename_folders_for_identifier(connection, project, old_identifier)
    except DriveError as error:
        logger.warning("Could not rename the Google Drive folders of project %s: %s", project_id, error.message)
        raise self.retry(countdown=60, exc=error) from error
    if renamed:
        logger.info("Project %s: renamed %s Google Drive folder(s) for its new Project ID.", project_id, renamed)


@shared_task
def follow_text_files(issue_id, removed, added):
    """Bin the files a work item's text stopped mentioning, and bring back the ones it mentions again."""
    follow_text(issue_id, removed, added)


@shared_task
def move_plane_attachments_to_drive(workspace_id, issue_id=None):
    """Move attachments from Plane's storage to Drive; the screen asked for it and watches the flag."""
    try:
        moved, failed = move_plane_attachments(workspace_id, issue_id)
        logger.info("Moved %s attachment(s) to Google Drive, %s failed.", moved, failed)
    finally:
        cache.delete(moving_key(workspace_id, issue_id))


@shared_task(bind=True, max_retries=3)
def move_new_issue_images(self, issue_id):
    """Move the images put in a new work item's description into its Drive folder, once it has one."""
    moved, pending = move_description_images(issue_id)
    if moved:
        logger.info("Moved %s image(s) of work item %s to Google Drive.", moved, issue_id)
    if pending:
        # An image whose upload has not been confirmed yet: once more a little later.
        raise self.retry(countdown=30)
