# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A new project gets its Drive folder without anybody asking."""

# Django imports
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

# Module imports
from plane.db.models import Project


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
