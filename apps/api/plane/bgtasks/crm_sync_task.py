# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Near-real-time mirroring of Plane work items and worklogs into a CRM.

Every work item in a mapped project gets its own CRM task, kept in step as the
title and description change. Sub work items are ordinary CRM tasks — the CRM
has no parent/child notion here. Comments, attachments and every other part of a
work item are deliberately never copied.

Worklogs and running timers are mirrored onto the matching CRM task's timer
rows, so hours land in the CRM as they are recorded rather than at month end.

All of it runs through Celery: the request path only enqueues, so a slow or
unreachable CRM never blocks a user's save.
"""

# Python imports
import logging

# Third party imports
from celery import shared_task
from django.conf import settings
from django.utils import timezone as dj_timezone

# Module imports
from plane.db.models import (
    CrmIntegration,
    CrmTaskLink,
    CrmTimerLink,
    CustomFieldValue,
    Issue,
    IssueWorkLog,
    Project,
    WorkspaceMember,
)
from plane.utils.crm_client import CrmApiClient, CrmApiError

logger = logging.getLogger(__name__)


# ─── Shared helpers ────────────────────────────────────────────────────────


def _get_client(integration):
    """Build an HTTP client for the integration, or None when it is unusable."""
    api_key = integration.get_api_key()
    if not integration.crm_api_url or not api_key:
        logger.warning(
            "CRM integration for workspace %s is missing URL or API key.",
            integration.workspace_id,
        )
        return None
    return CrmApiClient(
        base_url=integration.crm_api_url,
        api_key=api_key,
        verify=settings.CRM_VERIFY_SSL,
    )


def _active_integration(workspace_id):
    """The workspace's CRM integration when it is configured and switched on."""
    return CrmIntegration.objects.filter(workspace_id=workspace_id, is_active=True).first()


def _coerce_crm_project_id(value):
    """Return a positive int CRM project id from a stored value, else None."""
    if value is None or isinstance(value, (list, dict, bool)):
        return None
    try:
        crm_id = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return crm_id if crm_id > 0 else None


def _crm_project_id_for(integration, project):
    """Resolve the CRM project a Plane project maps to, or None when unmapped.

    An unmapped project is how a workspace keeps work out of the CRM, so this
    returning None is an ordinary outcome rather than an error.
    """
    if integration.project_mapping_source == CrmIntegration.ProjectMappingSource.IDENTIFIER:
        return _coerce_crm_project_id(project.identifier)

    if integration.crm_project_id_custom_field_id is None:
        return None
    value = (
        CustomFieldValue.objects.filter(
            project=project,
            custom_field_id=integration.crm_project_id_custom_field_id,
        )
        .values_list("value", flat=True)
        .first()
    )
    return _coerce_crm_project_id(value)


def _crm_staff_id_for(workspace_id, user):
    """Map a Plane user to a CRM staff id.

    The explicit ``crm_staff_id`` on the membership wins; otherwise the user's
    email is matched against CRM staff, which is the common case because both
    systems use the same addresses.
    """
    if user is None:
        return None

    member = WorkspaceMember.objects.filter(
        workspace_id=workspace_id, member=user, is_active=True
    ).first()
    if member and member.crm_staff_id:
        return member.crm_staff_id

    integration = _active_integration(workspace_id)
    if integration is None or not user.email:
        return None
    crm = _get_client(integration)
    if crm is None:
        return None

    try:
        staff = crm.get_staff()
    except CrmApiError as exc:
        logger.error("Could not load CRM staff for workspace %s: %s", workspace_id, exc)
        return None

    email = user.email.strip().lower()
    for entry in staff:
        if str(entry.get("email", "")).strip().lower() == email:
            return int(entry["id"])

    logger.warning(
        "No CRM staff matches %s in workspace %s; set the member's CRM staff id manually.",
        user.email,
        workspace_id,
    )
    return None


def _description_for(issue):
    """The work item body to mirror. Only the description travels to the CRM."""
    return issue.description_html or ""


# ─── Work items ────────────────────────────────────────────────────────────


@shared_task
def sync_issue_to_crm(issue_id):
    """Create or update the CRM task mirroring one work item."""
    issue = (
        Issue.objects.filter(id=issue_id)
        .select_related("project", "workspace")
        .first()
    )
    if issue is None:
        return

    integration = _active_integration(issue.workspace_id)
    if integration is None:
        return

    crm_project_id = _crm_project_id_for(integration, issue.project)
    if crm_project_id is None:
        return  # project is not mapped to the CRM

    crm = _get_client(integration)
    if crm is None:
        return

    link = CrmTaskLink.objects.filter(issue_id=issue.id).first()
    name = issue.name
    description = _description_for(issue)

    try:
        if link is None:
            created = crm.create_task(
                project_id=crm_project_id,
                name=name,
                description=description,
                month_year=dj_timezone.now().strftime("%Y-%m"),
            )
            crm_task_id = created.get("id")
            if not crm_task_id:
                logger.error("CRM did not return a task id for work item %s", issue.id)
                return
            CrmTaskLink.objects.create(
                workspace_id=issue.workspace_id,
                issue_id=issue.id,
                crm_task_id=crm_task_id,
                crm_project_id=crm_project_id,
                last_synced_at=dj_timezone.now(),
            )
        else:
            crm.update_task(link.crm_task_id, name=name, description=description)
            link.last_synced_at = dj_timezone.now()
            link.save(update_fields=["last_synced_at", "updated_at"])
    except CrmApiError as exc:
        logger.error("CRM sync failed for work item %s: %s", issue.id, exc)


@shared_task
def delete_issue_from_crm(workspace_id, crm_task_id):
    """Remove the CRM task for a work item that no longer exists in Plane.

    The ids are passed by value because the Plane rows are already gone by the
    time this runs.
    """
    integration = _active_integration(workspace_id)
    if integration is None:
        return
    crm = _get_client(integration)
    if crm is None:
        return

    try:
        crm.delete_task(crm_task_id)
    except CrmApiError as exc:
        logger.error("Could not delete CRM task %s: %s", crm_task_id, exc)


# ─── Worklogs and timers ───────────────────────────────────────────────────


def _timer_times(worklog):
    """Return ``(start, end)`` as unix timestamps; end is None while running.

    A running timer carries ``started_at`` and a NULL duration. A completed entry
    carries a duration, and the CRM wants an explicit end, so it is derived from
    the start plus that duration.
    """
    start = worklog.started_at or worklog.logged_at
    if start is None:
        return None, None
    start_ts = int(start.timestamp())

    if worklog.duration is None:
        return start_ts, None  # timer still running
    return start_ts, start_ts + int(worklog.duration)


@shared_task
def sync_worklog_to_crm(worklog_id):
    """Create or update the CRM timer mirroring one worklog / running timer."""
    worklog = (
        IssueWorkLog.objects.filter(id=worklog_id)
        .select_related("issue", "project", "logged_by")
        .first()
    )
    if worklog is None:
        return

    integration = _active_integration(worklog.workspace_id)
    if integration is None:
        return

    # The timer hangs off the CRM task, so the work item has to be mirrored first.
    link = CrmTaskLink.objects.filter(issue_id=worklog.issue_id).first()
    if link is None:
        sync_issue_to_crm(worklog.issue_id)
        link = CrmTaskLink.objects.filter(issue_id=worklog.issue_id).first()
        if link is None:
            return  # project unmapped, or the CRM rejected the task

    staff_id = _crm_staff_id_for(worklog.workspace_id, worklog.logged_by)
    if staff_id is None:
        return  # cannot attribute the hours to anyone in the CRM

    crm = _get_client(integration)
    if crm is None:
        return

    start_ts, end_ts = _timer_times(worklog)
    if start_ts is None:
        return

    timer_link = CrmTimerLink.objects.filter(worklog_id=worklog.id).first()
    note = worklog.description or ""

    try:
        if timer_link is None:
            created = crm.create_timer(
                task_id=link.crm_task_id,
                staff_id=staff_id,
                start_time=start_ts,
                end_time=end_ts,
                note=note,
            )
            crm_timer_id = created.get("id")
            if not crm_timer_id:
                logger.error("CRM did not return a timer id for worklog %s", worklog.id)
                return
            CrmTimerLink.objects.create(
                workspace_id=worklog.workspace_id,
                worklog_id=worklog.id,
                crm_timer_id=crm_timer_id,
                last_synced_at=dj_timezone.now(),
            )
        else:
            crm.update_timer(
                timer_link.crm_timer_id,
                start_time=start_ts,
                end_time=end_ts,
                note=note,
            )
            timer_link.last_synced_at = dj_timezone.now()
            timer_link.save(update_fields=["last_synced_at", "updated_at"])
    except CrmApiError as exc:
        logger.error("CRM sync failed for worklog %s: %s", worklog.id, exc)


@shared_task
def delete_worklog_from_crm(workspace_id, crm_timer_id):
    """Remove the CRM timer for a worklog that was deleted in Plane."""
    integration = _active_integration(workspace_id)
    if integration is None:
        return
    crm = _get_client(integration)
    if crm is None:
        return

    try:
        crm.delete_timer(crm_timer_id)
    except CrmApiError as exc:
        logger.error("Could not delete CRM timer %s: %s", crm_timer_id, exc)


# ─── Backfill ──────────────────────────────────────────────────────────────


@shared_task
def backfill_workspace_to_crm(integration_id):
    """Push every existing work item and worklog of a workspace to the CRM once.

    Anything already linked is updated rather than duplicated, so running this
    twice is safe.
    """
    integration = CrmIntegration.objects.filter(id=integration_id).first()
    if integration is None:
        return

    projects = Project.objects.filter(workspace_id=integration.workspace_id)
    mapped_project_ids = [p.id for p in projects if _crm_project_id_for(integration, p) is not None]
    if not mapped_project_ids:
        return

    issue_ids = list(
        Issue.objects.filter(project_id__in=mapped_project_ids).values_list("id", flat=True)
    )
    for issue_id in issue_ids:
        sync_issue_to_crm(issue_id)

    worklog_ids = list(
        IssueWorkLog.objects.filter(project_id__in=mapped_project_ids).values_list("id", flat=True)
    )
    for worklog_id in worklog_ids:
        sync_worklog_to_crm(worklog_id)

    integration.last_synced_at = dj_timezone.now()
    integration.save(update_fields=["last_synced_at", "updated_at"])

    logger.info(
        "CRM backfill for workspace %s pushed %s work items and %s worklogs.",
        integration.workspace_id,
        len(issue_ids),
        len(worklog_ids),
    )
