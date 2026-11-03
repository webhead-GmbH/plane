# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Files in a work item's description and comments follow the text they are in.

An image or a file put in the text lives in the work item's Drive folder. When
the last mention of it leaves the text (it is deleted from the description, or
its comment is edited or deleted), it goes to Drive's bin; when it comes back
(an undo, an older version restored), it comes out of the bin again.

Attachments are not affected: they are listed on their own and removed there.
"""

# Python imports
import logging
import re

# Django imports
from django.db.models import Q
from django.utils import timezone

# Module imports
from plane.db.models import Issue, IssueComment
from plane.gdrive.client import DriveClient, DriveError
from plane.gdrive.models import DriveConnection, DriveFile

logger = logging.getLogger(__name__)

TEXT_SOURCES = (DriveFile.Source.DESCRIPTION, DriveFile.Source.COMMENT)

# An image in the text points at the file by its Plane id ("gdrive-<uuid>"); a
# link to any other file is the file's Drive address, with Google's id in it.
_PLANE_ID = re.compile(r"(?:gdrive-|/drive/files/)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_GOOGLE_ID = re.compile(r"https://(?:drive|docs)\.google\.com/[^\"'\s<>]*?/d/([A-Za-z0-9_-]{10,})")


def references(html):
    """The Drive files a piece of text points at, as "plane:<id>" and "google:<id>"."""
    if not html:
        return frozenset()
    return frozenset(
        [f"plane:{found}" for found in _PLANE_ID.findall(html)]
        + [f"google:{found}" for found in _GOOGLE_ID.findall(html)]
    )


def _names(drive_file):
    return {f"plane:{drive_file.id}", f"google:{drive_file.drive_file_id}"}


def _mentioned(issue_id, names):
    """The issue's text files that any of these names point at, in the bin or not."""
    plane_ids = [name.split(":", 1)[1] for name in names if name.startswith("plane:")]
    google_ids = [name.split(":", 1)[1] for name in names if name.startswith("google:")]
    return DriveFile.all_objects.filter(
        Q(pk__in=plane_ids) | Q(drive_file_id__in=google_ids),
        issue_id=issue_id,
        source__in=TEXT_SOURCES,
        state=DriveFile.State.UPLOADED,
    )


def _still_mentioned(issue_id):
    description = Issue.all_objects.filter(pk=issue_id).values_list("description_html", flat=True).first()
    comments = IssueComment.objects.filter(issue_id=issue_id).values_list("comment_html", flat=True)
    found = set(references(description))
    for html in comments:
        found |= references(html)
    return found


def follow_text(issue_id, removed, added):
    """Bin the files no text mentions any more, and bring back the ones mentioned again."""
    removed_files = list(_mentioned(issue_id, removed)) if removed else []
    added_files = [item for item in _mentioned(issue_id, added) if item.deleted_at] if added else []
    if not removed_files and not added_files:
        return
    connection = DriveConnection.objects.filter(workspace_id=(removed_files or added_files)[0].workspace_id).first()
    drive = DriveClient(connection) if connection and connection.is_connected else None
    still = _still_mentioned(issue_id)

    for drive_file in removed_files:
        if drive_file.deleted_at or _names(drive_file) & still:
            continue
        try:
            if drive:
                drive.trash(drive_file.drive_file_id)
        except DriveError as error:
            if error.reason != "notFound":
                logger.warning("Could not put Drive file %s in the bin: %s", drive_file.id, error.message)
                continue
        # Updated in place: saving the record in a worker, with nobody signed in, would clear its uploader.
        DriveFile.objects.filter(pk=drive_file.pk).update(deleted_at=timezone.now())

    for drive_file in added_files:
        if not _names(drive_file) & still:
            continue
        try:
            if drive:
                drive.untrash(drive_file.drive_file_id)
        except DriveError as error:
            logger.warning("Could not take Drive file %s out of the bin: %s", drive_file.id, error.message)
            continue
        DriveFile.all_objects.filter(pk=drive_file.pk).update(deleted_at=None)
