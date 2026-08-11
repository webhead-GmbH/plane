# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Fan work item and worklog changes out to the CRM as they happen.

Signals are used rather than dispatching from each view because a work item can
be written from several places — the web app, the external REST API, intake and
bulk operations — and every one of them has to reach the CRM. Each handler only
enqueues a Celery task, and only after the surrounding transaction commits, so a
rolled-back save never reaches the CRM and a slow CRM never delays a response.
"""

# Django imports
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

# Module imports
from plane.db.models import (
    CrmIntegration,
    CrmTaskLink,
    CrmTimerLink,
    CustomFieldValue,
    Issue,
    IssueAssignee,
    IssueWorkLog,
    Project,
)

# Fields whose change is worth a CRM round-trip. Comments, attachments and links
# deliberately stay out of the CRM; state travels because the CRM task's status
# tracks it, and assignees are handled by their own m2m signal below.
MIRRORED_ISSUE_FIELDS = {
    "name",
    "description_html",
    "state",
    "priority",
    "start_date",
    "target_date",
}


def _enqueue(fn, *args, **kwargs):
    """Run a Celery dispatch once the current transaction commits."""
    transaction.on_commit(lambda: fn.delay(*args, **kwargs))


@receiver(post_save, sender=Issue)
def issue_saved(sender, instance, created, update_fields=None, **kwargs):
    """Mirror a new or edited work item onto its CRM task."""
    # A save that only touched unrelated fields does not need the CRM.
    if not created and update_fields is not None:
        if not (set(update_fields) & MIRRORED_ISSUE_FIELDS):
            return

    from plane.bgtasks.crm_sync_task import sync_issue_to_crm

    _enqueue(sync_issue_to_crm, str(instance.id))


@receiver(pre_delete, sender=Issue)
def issue_deleting(sender, instance, **kwargs):
    """Remember the CRM task id before the link row disappears with the issue."""
    link = CrmTaskLink.objects.filter(issue_id=instance.id).first()
    if link is not None:
        # stash on the instance so post_delete can still read it
        instance._crm_task_id = link.crm_task_id
        instance._crm_workspace_id = link.workspace_id


@receiver(post_delete, sender=Issue)
def issue_deleted(sender, instance, **kwargs):
    """Delete the mirrored CRM task once the work item is really gone."""
    crm_task_id = getattr(instance, "_crm_task_id", None)
    workspace_id = getattr(instance, "_crm_workspace_id", None)
    if not crm_task_id or not workspace_id:
        return

    from plane.bgtasks.crm_sync_task import delete_issue_from_crm

    _enqueue(delete_issue_from_crm, str(workspace_id), int(crm_task_id))


@receiver(post_save, sender=IssueAssignee)
@receiver(post_delete, sender=IssueAssignee)
def issue_assignee_changed(sender, instance, **kwargs):
    """Re-sync the work item when someone is assigned or unassigned.

    The whole assignee set is pushed rather than the delta, so the CRM ends up
    with exactly Plane's list. On the CRM side an unassign removes the assignment
    but keeps the person as a follower.
    """
    from plane.bgtasks.crm_sync_task import sync_issue_to_crm

    _enqueue(sync_issue_to_crm, str(instance.issue_id))


@receiver(post_save, sender=IssueWorkLog)
def worklog_saved(sender, instance, created, **kwargs):
    """Mirror a started, stopped, logged or edited worklog onto the CRM timer."""
    from plane.bgtasks.crm_sync_task import sync_worklog_to_crm

    _enqueue(sync_worklog_to_crm, str(instance.id))


@receiver(pre_delete, sender=IssueWorkLog)
def worklog_deleting(sender, instance, **kwargs):
    link = CrmTimerLink.objects.filter(worklog_id=instance.id).first()
    if link is not None:
        instance._crm_timer_id = link.crm_timer_id
        instance._crm_workspace_id = link.workspace_id


@receiver(post_delete, sender=IssueWorkLog)
def worklog_deleted(sender, instance, **kwargs):
    crm_timer_id = getattr(instance, "_crm_timer_id", None)
    workspace_id = getattr(instance, "_crm_workspace_id", None)
    if not crm_timer_id or not workspace_id:
        return

    from plane.bgtasks.crm_sync_task import delete_worklog_from_crm

    _enqueue(delete_worklog_from_crm, str(workspace_id), int(crm_timer_id))


# ─── Project-mapping changes → move the project's CRM tasks ──────────────────


@receiver(post_save, sender=CustomFieldValue)
@receiver(post_delete, sender=CustomFieldValue)
def project_crm_id_value_changed(sender, instance, **kwargs):
    """When the custom field that holds a project's CRM id is written, remap it.

    Gated tightly: only a project-scoped value of the field the active integration
    is actually mapped to matters, so writing any other project custom field does
    not enqueue anything.
    """
    if not instance.project_id or instance.issue_id:
        return

    integration = CrmIntegration.objects.filter(
        workspace_id=instance.workspace_id,
        is_active=True,
        project_mapping_source=CrmIntegration.ProjectMappingSource.CUSTOM_FIELD,
        crm_project_id_custom_field_id=instance.custom_field_id,
    ).first()
    if integration is None:
        return

    from plane.bgtasks.crm_sync_task import remap_project_crm_tasks

    _enqueue(remap_project_crm_tasks, str(instance.project_id))


@receiver(post_save, sender=Project)
def project_identifier_maybe_changed(sender, instance, created, **kwargs):
    """In identifier mode, a project save may have changed its CRM id.

    Fires on any project save in that mode; the remap self-filters (nothing is
    moved when the identifier did not actually change), which avoids tracking the
    old value on a model that is saved for many unrelated reasons.
    """
    integration = CrmIntegration.objects.filter(
        workspace_id=instance.workspace_id,
        is_active=True,
        project_mapping_source=CrmIntegration.ProjectMappingSource.IDENTIFIER,
    ).first()
    if integration is None:
        return

    from plane.bgtasks.crm_sync_task import remap_project_crm_tasks

    _enqueue(remap_project_crm_tasks, str(instance.id))


@receiver(post_save, sender=CrmIntegration)
def integration_mapping_config_changed(sender, instance, created, **kwargs):
    """Reconcile the whole workspace when the mapping config or activation changes.

    Switching the mapping source or the mapped custom field re-resolves every
    project; re-activating catches repoints made while the sync was off. An
    inactive integration can move nothing, so those transitions are ignored.
    """
    if created or not instance.is_active:
        return
    if not instance.remap_relevant_changes():
        return

    from plane.bgtasks.crm_sync_task import remap_workspace_crm_tasks

    _enqueue(remap_workspace_crm_tasks, str(instance.workspace_id))
