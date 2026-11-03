# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A new project gets its Drive folder without anybody asking, and files in text follow the text."""

# Django imports
from django.db import transaction
from django.db.models.signals import post_init, post_save, pre_save
from django.dispatch import receiver

# Module imports
from plane.db.models import Issue, IssueComment, Project
from plane.gdrive.models import DriveFile
from plane.gdrive.references import references
from plane.gdrive.services import in_drive_instead, stored_images


@receiver(post_save, sender=Project)
def link_new_project_to_drive(sender, instance, created, **kwargs):
    if not created:
        return
    from plane.gdrive.tasks import link_new_project_folder

    project_id = str(instance.id)
    user_id = str(instance.created_by_id) if instance.created_by_id else None
    # After the commit, so the task can see the project; in a task, so creating a
    # project never waits on Google.
    transaction.on_commit(lambda: link_new_project_folder.delay(project_id, user_id))


def _follow(issue_id, before, after):
    """Hand the files that left the text, or came back to it, to a task: Google is not waited on."""
    if before == after:
        return
    old, new = references(before), references(after)
    removed, added = sorted(old - new), sorted(new - old)
    if not removed and not added:
        return
    from plane.gdrive.tasks import follow_text_files

    issue = str(issue_id)
    transaction.on_commit(lambda: follow_text_files.delay(issue, removed, added))


@receiver(post_save, sender=IssueComment)
def follow_comment_files(sender, instance, created, **kwargs):
    # The comment as it was loaded (kept by its change tracker until the save
    # ends), and as it is now; a deleted comment mentions nothing any more.
    before = "" if created else instance.old_values.get("comment_html", "")
    after = "" if instance.deleted_at else instance.comment_html
    _follow(instance.issue_id, before, after)


@receiver(post_init, sender=Issue)
def remember_description(sender, instance, **kwargs):
    # Read from the instance's own fields, so a query that left the description
    # out does not fetch it here for every work item it loads.
    instance._drive_description = instance.__dict__.get("description_html")


@receiver(post_save, sender=Issue)
def follow_description_files(sender, instance, created, update_fields=None, **kwargs):
    if update_fields is not None and "description_html" not in update_fields:
        return
    before = getattr(instance, "_drive_description", None)
    after = instance.__dict__.get("description_html")
    instance._drive_description = after
    if created or before is None or after is None:
        return
    _follow(instance.id, before, after)


@receiver(post_save, sender=Issue)
def move_new_issue_images_to_drive(sender, instance, created, **kwargs):
    if not created or "<image-component" not in (instance.__dict__.get("description_html") or ""):
        return
    from plane.gdrive.tasks import move_new_issue_images

    issue = str(instance.id)
    # A few seconds on: the page that made the work item attaches its images to it right after.
    transaction.on_commit(lambda: move_new_issue_images.apply_async(args=[issue], countdown=3))


@receiver(pre_save, sender=Issue)
def keep_moved_images_in_drive(sender, instance, update_fields=None, **kwargs):
    """An editor opened before its images moved saves them by their old ids; point them at Drive again."""
    if instance._state.adding or (update_fields is not None and "description_html" not in update_fields):
        return
    html = instance.__dict__.get("description_html")
    old_ids = stored_images(html)
    if not old_ids:
        return
    moved = DriveFile.all_objects.filter(issue_id=instance.id, moved_from__in=old_ids).values_list("moved_from", "id")
    if moved:
        instance.description_html = in_drive_instead(html, {str(old): str(new) for old, new in moved})
