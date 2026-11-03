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
from plane.gdrive.services import link_new_project, move_plane_attachments, moving_key

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
