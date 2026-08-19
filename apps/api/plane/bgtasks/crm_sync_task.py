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
from datetime import timedelta

# Third party imports
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone as dj_timezone
from django.utils.html import escape

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


def _crm_staff_by_email(workspace_id):
    """CRM staff keyed by lower-cased email.

    Returns None when the list could not be read and ``{}`` when the CRM
    genuinely has no usable staff. The two must stay apart: "nobody has an
    account" is a fact worth acting on, while "the request failed" is not, and
    treating a failed call as an empty roster would declare the whole team
    unmatched and rewrite every task description off a transient error.
    """
    integration = _active_integration(workspace_id)
    if integration is None:
        return None
    crm = _get_client(integration)
    if crm is None:
        return None

    try:
        staff = crm.get_staff()
    except CrmApiError as exc:
        logger.error("Could not load CRM staff for workspace %s: %s", workspace_id, exc)
        return None

    return {
        str(entry.get("email", "")).strip().lower(): int(entry["id"])
        for entry in staff
        if entry.get("email") and entry.get("id")
    }


def _crm_staff_id_for(workspace_id, user, staff_by_email=None):
    """Map a Plane user to a CRM staff id.

    The explicit ``crm_staff_id`` on the membership wins; otherwise the user's
    email is matched against CRM staff, which is the common case because both
    systems use the same addresses. Callers that already hold the staff map pass
    it in so one sync costs a single CRM round-trip.
    """
    if user is None:
        return None

    member = WorkspaceMember.objects.filter(
        workspace_id=workspace_id, member=user, is_active=True
    ).first()
    if member and member.crm_staff_id:
        return member.crm_staff_id

    if not user.email:
        return None

    if staff_by_email is None:
        staff_by_email = _crm_staff_by_email(workspace_id)
    staff_id = (staff_by_email or {}).get(user.email.strip().lower())
    if staff_id is None:
        logger.warning(
            "No CRM staff matches %s in workspace %s; set the member's CRM staff id manually.",
            user.email,
            workspace_id,
        )
    return staff_id


# ─── Hours logged by people the CRM has no account for ─────────────────────
#
# A worklog can only become a CRM timer when its author maps to a CRM staff id.
# Rather than dropping the hours of everyone else, they are written onto the CRM
# task itself, so the time is still visible and invoiceable. The block is
# delimited purely so it reads as one unit — it is rebuilt from the worklogs on
# every sync rather than parsed back out, because Plane owns the description and
# overwrites it wholesale.
#
# Styling is inline on every element: the CRM stores this as task description HTML and
# drops <style> blocks, so a stylesheet would not survive. Borders and muted text use
# grey/alpha values that stay readable on both the CRM's light and dark themes, and the
# date and duration cells never wrap — wrapped timestamps were what made this look messy.
_CELL = "border:1px solid rgba(128,128,128,.35);padding:7px 10px;vertical-align:top"
_HEAD = _CELL + ";text-align:left;font-weight:600;white-space:nowrap"
_NOWRAP = _CELL + ";white-space:nowrap"
_NUM = _CELL + ";white-space:nowrap;text-align:right"
_HEAD_NUM = _CELL + ";font-weight:600;white-space:nowrap;text-align:right"
_MUTED = "font-size:12px;color:#888"

UNMATCHED_NOTE_START = "<!-- plane:unmatched-worklogs:start -->"
UNMATCHED_NOTE_END = "<!-- plane:unmatched-worklogs:end -->"


def _local_datetime(value):
    """Render a timestamp in the server's timezone, as the CRM displays them.

    Date and time go on separate lines: on one line these columns are wide enough
    to squeeze the note column out of the CRM's task panel entirely.
    """
    if value is None:
        return "—"
    local = dj_timezone.localtime(value)
    return f'{local.strftime("%Y-%m-%d")}<br>{local.strftime("%H:%M")}'


def _duration_hm(seconds):
    """Render a duration as H:MM, the shape a timesheet is read in."""
    total = max(int(seconds or 0), 0)
    return f"{total // 3600}:{(total % 3600) // 60:02d}"


def _unmatched_worklogs(issue, staff_by_email):
    """Worklogs on this work item whose hours are not in the CRM as a timer.

    A worklog that already has a CRM timer is never listed, whatever its author
    looks like today: ``get_staff`` only returns *active* staff, so someone who
    leaves stops matching, and going by the author alone would re-list hours the
    CRM already holds and count them twice.
    """
    worklogs = list(
        IssueWorkLog.objects.filter(issue_id=issue.id)
        .select_related("logged_by")
        .order_by("started_at", "logged_at")
    )
    users = [wl.logged_by for wl in worklogs if wl.logged_by_id]
    if not users:
        return []

    # A member with a manual crm_staff_id is matched even when no email lines up.
    overrides = set(
        WorkspaceMember.objects.filter(
            workspace_id=issue.workspace_id,
            member__in=users,
            is_active=True,
            # >0, not just set: the resolver treats 0 as "no override" and would
            # fall through to email, so counting it as matched here would leave
            # those hours in neither the timers nor the table.
            crm_staff_id__gt=0,
        ).values_list("member_id", flat=True)
    )
    mirrored = set(
        CrmTimerLink.objects.filter(worklog__in=worklogs).values_list("worklog_id", flat=True)
    )

    unmatched = []
    for worklog in worklogs:
        user = worklog.logged_by
        if user is None or worklog.id in mirrored or user.id in overrides:
            continue
        if user.email and staff_by_email.get(user.email.strip().lower()):
            continue
        unmatched.append(worklog)
    return unmatched


def _unmatched_worklog_note(issue, staff_by_email):
    """An HTML table of the hours the CRM cannot attribute to any of its staff.

    Returns "" when everyone who logged time on this work item does have a CRM
    account, so the table only ever exists while there is something it is holding.

    None means the staff list could not be read, so nothing is written rather
    than declaring the whole team unmatched off a failed request. An empty map is
    a real answer — a CRM with no staff matches nobody — and does build the table.
    """
    if staff_by_email is None:
        return ""

    worklogs = _unmatched_worklogs(issue, staff_by_email)
    if not worklogs:
        return ""

    rows = []
    total = 0
    for worklog in worklogs:
        user = worklog.logged_by
        started = worklog.started_at or worklog.logged_at
        if worklog.duration is None:
            # Still running: it gets a real end and duration when it is stopped.
            ended_cell = "—"
            duration_cell = "running"
        else:
            ended = started + timedelta(seconds=int(worklog.duration)) if started else None
            ended_cell = _local_datetime(ended)
            duration_cell = _duration_hm(worklog.duration)
            total += int(worklog.duration)

        rows.append(
            "<tr>"
            f'<td style="{_CELL}">{escape(user.display_name or user.email or "—")}'
            f'<br><span style="{_MUTED}">{escape(user.email or "")}</span></td>'
            f'<td style="{_NOWRAP}">{_local_datetime(started)}</td>'
            f'<td style="{_NOWRAP}">{ended_cell}</td>'
            f'<td style="{_NUM}">{duration_cell}</td>'
            f'<td style="{_CELL}">{escape(worklog.description or "")}</td>'
            "</tr>"
        )

    # The CRM renders its own timers in the CRM's timezone, so the column says
    # which one these are in rather than leaving billable times ambiguous.
    tz_label = escape(dj_timezone.get_current_timezone_name())
    return (
        # A rule keeps the synced block visibly apart from the body written in Plane.
        '<hr style="margin:18px 0 14px;border:0;border-top:1px solid rgba(128,128,128,.35)">'
        '<p style="margin:0 0 3px"><strong>Time logged in Plane by people without a CRM account</strong></p>'
        f'<p style="margin:0 0 10px;{_MUTED}">These entries could not be attached to a CRM staff '
        'member, so they are recorded here instead of being lost.</p>'
        '<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px">'
        f'<thead><tr><th style="{_HEAD}">User</th><th style="{_HEAD}">Start ({tz_label})</th>'
        f'<th style="{_HEAD}">End ({tz_label})</th>'
        f'<th style="{_HEAD_NUM}">Duration</th><th style="{_HEAD}">Note</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody>"
        f'<tfoot><tr><td colspan="3" style="{_CELL};text-align:right"><strong>Total</strong></td>'
        f'<td style="{_NUM}"><strong>{_duration_hm(total)}</strong></td>'
        f'<td style="{_CELL}"></td></tr></tfoot>'
        "</table>"
    )


def _description_for(issue, staff_by_email=None):
    """The work item body to mirror, plus any hours the CRM cannot attribute.

    Only the description travels to the CRM. The unmatched-hours table is built
    here rather than appended elsewhere because every sync rewrites the whole
    description — a note added by any other path would be lost on the next save.
    """
    base = issue.description_html or ""
    if staff_by_email is None:
        staff_by_email = _crm_staff_by_email(issue.workspace_id)

    note = _unmatched_worklog_note(issue, staff_by_email)
    if not note:
        return base
    return f"{base}{UNMATCHED_NOTE_START}{note}{UNMATCHED_NOTE_END}"


# Plane states are per-project and freely renamed, but every one belongs to a
# fixed group, so the group is what maps onto the CRM's fixed status list.
# The CRM has no "cancelled", and treating a cancelled item as complete would
# inflate delivered work, so it maps to Not Started instead.
CRM_STATUS_NOT_STARTED = 1
CRM_STATUS_IN_PROGRESS = 4
CRM_STATUS_COMPLETE = 5

STATE_GROUP_TO_CRM_STATUS = {
    "backlog": CRM_STATUS_NOT_STARTED,
    "triage": CRM_STATUS_NOT_STARTED,
    "unstarted": CRM_STATUS_NOT_STARTED,
    "started": CRM_STATUS_IN_PROGRESS,
    "completed": CRM_STATUS_COMPLETE,
    "cancelled": CRM_STATUS_NOT_STARTED,
}


def _crm_status_for(issue):
    """Map the work item's state group onto a CRM task status."""
    group = getattr(issue.state, "group", None) if issue.state_id else None
    return STATE_GROUP_TO_CRM_STATUS.get(group, CRM_STATUS_NOT_STARTED)


# The CRM's four priorities line up with Plane's, except that Plane also has
# "none"; an unprioritised item lands on the CRM's own default of Medium.
CRM_PRIORITY_MEDIUM = 2

PRIORITY_TO_CRM = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "urgent": 4,
    "none": CRM_PRIORITY_MEDIUM,
}


def _crm_priority_for(issue):
    """Map the work item's priority onto a CRM task priority."""
    return PRIORITY_TO_CRM.get(issue.priority, CRM_PRIORITY_MEDIUM)


def _iso_date(value):
    """Render a date for the CRM, or an empty string to clear it."""
    return value.isoformat() if value else ""


def _work_item_url(issue):
    """Deep link back to the work item, shown on the CRM task."""
    base = (settings.WEB_URL or "").rstrip("/")
    if not base:
        return None
    return f"{base}/{issue.workspace.slug}/projects/{issue.project_id}/issues/{issue.id}"


def _assignee_staff_ids(issue, staff_by_email=None):
    """CRM staff ids for everyone currently assigned to the work item.

    Assignees that cannot be matched to CRM staff are dropped rather than
    guessed at; the warning from the resolver is the trail for fixing it.
    The staff list is fetched once and shared across assignees, so a work item
    with several people costs one CRM round-trip rather than one per person.
    """
    # Read through IssueAssignee rather than issue.assignees: unassigning
    # soft-deletes the through row, and the m2m descriptor joins that table
    # directly, so it would still hand back people who are no longer assigned.
    users = [ia.assignee for ia in IssueAssignee.objects.filter(issue=issue).select_related("assignee")]
    if not users:
        return []

    if staff_by_email is None:
        staff_by_email = _crm_staff_by_email(issue.workspace_id)
    overrides = dict(
        WorkspaceMember.objects.filter(
            workspace_id=issue.workspace_id,
            member__in=users,
            is_active=True,
            # >0, not just set: the resolver treats 0 as "no override" and would
            # fall through to email, so counting it as matched here would leave
            # those hours in neither the timers nor the table.
            crm_staff_id__gt=0,
        ).values_list("member_id", "crm_staff_id")
    )

    staff_ids = []
    for user in users:
        staff_id = overrides.get(user.id)
        if staff_id is None and user.email:
            staff_id = staff_by_email.get(user.email.strip().lower())
        if staff_id is None:
            logger.warning(
                "No CRM staff matches %s; work item %s will sync without them assigned.",
                user.email,
                issue.id,
            )
            continue
        staff_ids.append(staff_id)
    return staff_ids


# ─── Work items ────────────────────────────────────────────────────────────


@shared_task
def sync_issue_to_crm(issue_id):
    """Create or update the CRM task mirroring one work item.

    Saving a work item and assigning someone fire separate signals that can land
    in different workers at the same time. Both would see no link yet and each
    create a CRM task, so the work item row is locked for the duration and the
    second run sees the link the first one wrote.
    """
    with transaction.atomic():
        _sync_issue_locked(issue_id)


def _sync_issue_locked(issue_id):
    # Locking the work item serialises concurrent syncs of the same item.
    if not Issue.objects.select_for_update().filter(id=issue_id).exists():
        return

    issue = (
        Issue.objects.filter(id=issue_id)
        .select_related("project", "workspace", "state")
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

    # One staff fetch feeds both the assignee mapping and the unmatched-hours
    # table, and is skipped entirely for a work item with neither — the common
    # case, which must not start paying for a CRM round-trip it has no use for.
    needs_staff = (
        IssueAssignee.objects.filter(issue=issue).exists()
        or IssueWorkLog.objects.filter(issue_id=issue.id).exists()
    )
    staff_by_email = _crm_staff_by_email(issue.workspace_id) if needs_staff else {}
    if staff_by_email is None:
        # Pushing now would drop every assignee and strip the unmatched-hours
        # table off the task. Leave the CRM as it is; the next save re-syncs.
        logger.error(
            "Skipping CRM sync of work item %s: the CRM staff list could not be read.",
            issue.id,
        )
        return

    description = _description_for(issue, staff_by_email)
    status = _crm_status_for(issue)
    assignee_ids = _assignee_staff_ids(issue, staff_by_email)
    priority = _crm_priority_for(issue)
    startdate = _iso_date(issue.start_date)
    duedate = _iso_date(issue.target_date)

    try:
        if link is None:
            created = crm.create_task(
                project_id=crm_project_id,
                name=name,
                description=description,
                month_year=dj_timezone.now().strftime("%Y-%m"),
                work_item_id=str(issue.id),
                work_item_url=_work_item_url(issue),
                status=status,
                assignee_ids=assignee_ids,
                priority=priority,
                startdate=startdate,
                duedate=duedate,
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
            crm.update_task(
                link.crm_task_id,
                name=name,
                description=description,
                status=status,
                assignee_ids=assignee_ids,
                priority=priority,
                startdate=startdate,
                duedate=duedate,
            )
            link.last_synced_at = dj_timezone.now()
            link.save(update_fields=["last_synced_at", "updated_at"])
    except CrmApiError as exc:
        logger.error("CRM sync failed for work item %s: %s", issue.id, exc)
        return

    _mirror_newly_matched_worklogs(issue, staff_by_email)


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


def _unmirror_worklog(worklog, integration):
    """Take a deleted worklog's hours back out of the CRM.

    Plane soft-deletes a worklog, which reaches this module as an ordinary save
    rather than a delete, so removal is handled here rather than from a delete
    signal. The CRM timer goes if there was one, and the work item is re-synced
    so an unattributed entry drops out of the description table too.
    """
    # all_objects: the soft delete cascades to the link, and that can land first.
    link = CrmTimerLink.all_objects.filter(worklog_id=worklog.id).first()
    if link is not None:
        crm = _get_client(integration)
        if crm is not None:
            try:
                crm.delete_timer(link.crm_timer_id)
            except CrmApiError as exc:
                logger.error("Could not delete CRM timer %s: %s", link.crm_timer_id, exc)
        link.delete()

    sync_issue_to_crm(str(worklog.issue_id))


def _mirror_newly_matched_worklogs(issue, staff_by_email):
    """Push hours that were logged before their author had a CRM account.

    Once the person exists in the CRM their entries leave the description table,
    so they have to become real timers in the same breath or the hours would
    simply disappear from the CRM.
    """
    linked = set(
        CrmTimerLink.objects.filter(worklog__issue_id=issue.id).values_list("worklog_id", flat=True)
    )
    unmatched = {worklog.id for worklog in _unmatched_worklogs(issue, staff_by_email)}
    for worklog_id in IssueWorkLog.objects.filter(issue_id=issue.id).values_list("id", flat=True):
        if worklog_id in linked or worklog_id in unmatched:
            continue
        sync_worklog_to_crm.delay(str(worklog_id))


@shared_task
def sync_worklog_to_crm(worklog_id):
    """Create or update the CRM timer mirroring one worklog / running timer."""
    # all_objects: deleting a worklog in Plane is a soft delete, so removal
    # arrives here as a save of a row the default manager no longer returns.
    worklog = (
        IssueWorkLog.all_objects.filter(id=worklog_id)
        .select_related("issue", "project", "logged_by")
        .first()
    )
    if worklog is None:
        return

    integration = _active_integration(worklog.workspace_id)
    if integration is None:
        return

    if worklog.deleted_at is not None:
        _unmirror_worklog(worklog, integration)
        return

    staff_by_email = _crm_staff_by_email(worklog.workspace_id)
    if staff_by_email is None:
        return  # roster unreadable; the next save syncs it

    staff_id = _crm_staff_id_for(worklog.workspace_id, worklog.logged_by, staff_by_email)
    if staff_id is None:
        # Nobody in the CRM to hang a timer off, so the hours go onto the task
        # description instead of being dropped. Routed through the work item sync
        # so the description is written under the same row lock as every other
        # description write, and so the task is created when it does not exist.
        sync_issue_to_crm(str(worklog.issue_id))
        return

    # The timer hangs off the CRM task, so the work item has to be mirrored first.
    link = CrmTaskLink.objects.filter(issue_id=worklog.issue_id).first()
    if link is None:
        sync_issue_to_crm(worklog.issue_id)
        link = CrmTaskLink.objects.filter(issue_id=worklog.issue_id).first()
        if link is None:
            return  # project unmapped, or the CRM rejected the task

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

    # Also reconcile project mappings, so the Backfill button doubles as a
    # "fix any drift" action after a project id was corrected.
    for project_id in mapped_project_ids:
        remap_project_crm_tasks(str(project_id))

    integration.last_synced_at = dj_timezone.now()
    integration.save(update_fields=["last_synced_at", "updated_at"])

    logger.info(
        "CRM backfill for workspace %s pushed %s work items and %s worklogs.",
        integration.workspace_id,
        len(issue_ids),
        len(worklog_ids),
    )


# ─── Project remap (a project's CRM id changed) ──────────────────────────────


@shared_task
def remap_project_crm_tasks(project_id):
    """Move a project's mirrored CRM tasks after its CRM project id changed.

    Fired whenever the mapping *might* have changed (a project or custom-field
    save). It resolves the current CRM project id and, for each linked task still
    filed under a different one, enqueues a per-task move. When nothing changed no
    task differs and nothing is enqueued, so the common no-op case is one query.

    The links are read directly (not via Issue.objects) so tasks of soft-deleted
    work items — whose CRM task still exists — are moved too.
    """
    project = Project.objects.filter(id=project_id).select_related("workspace").first()
    if project is None:
        return

    integration = _active_integration(project.workspace_id)
    if integration is None:
        return

    target = _crm_project_id_for(integration, project)
    if target is None:
        # Mapping cleared or now unresolvable (e.g. a non-numeric identifier).
        # Existing tasks are left where they are rather than orphaned or deleted.
        logger.info(
            "CRM remap for project %s skipped: mapping resolves to no CRM project.",
            project_id,
        )
        return

    stale_link_ids = list(
        CrmTaskLink.objects.filter(issue__project_id=project_id)
        .exclude(crm_project_id=target)
        .values_list("id", flat=True)
    )
    for link_id in stale_link_ids:
        move_crm_task_to_crm_project.delay(str(link_id))


@shared_task
def move_crm_task_to_crm_project(link_id):
    """Move one linked CRM task to whatever CRM project its Plane project now maps to.

    The task carries only the link id and re-resolves the target inside a row
    lock, never a value captured at enqueue time. That closes the race between two
    remaps: whichever runs second re-reads the current mapping and either no-ops
    or corrects, so a task can't be stranded under a superseded id.
    """
    with transaction.atomic():
        link = CrmTaskLink.objects.select_for_update().filter(id=link_id).first()
        if link is None:
            return

        # all_objects: the work item may be soft-deleted while its CRM task lives on.
        project_id = (
            Issue.all_objects.filter(id=link.issue_id).values_list("project_id", flat=True).first()
        )
        if project_id is None:
            return
        project = Project.objects.filter(id=project_id).select_related("workspace").first()
        if project is None:
            return

        integration = _active_integration(link.workspace_id)
        if integration is None:
            return

        target = _crm_project_id_for(integration, project)
        if target is None or link.crm_project_id == target:
            return  # unresolvable now, or already correct

        crm = _get_client(integration)
        if crm is None:
            return

        try:
            crm.move_task(link.crm_task_id, target)
        except CrmApiError as exc:
            # Leave the link stale so a later trigger (or a backfill) retries;
            # advancing it now would permanently skip a task that never moved.
            logger.error("CRM move failed for task %s -> project %s: %s", link.crm_task_id, target, exc)
            return

        link.crm_project_id = target
        link.last_synced_at = dj_timezone.now()
        link.save(update_fields=["crm_project_id", "last_synced_at", "updated_at"])


@shared_task
def remap_workspace_crm_tasks(workspace_id):
    """Reconcile every project in a workspace after the mapping *config* changed.

    Triggered when the integration's mapping source or mapped custom field
    changes, or when it is re-activated — any of which can change what projects
    resolve to. Fans out to the per-project remap, which self-filters.
    """
    integration = _active_integration(workspace_id)
    if integration is None:
        return
    for project_id in Project.objects.filter(workspace_id=workspace_id).values_list("id", flat=True):
        remap_project_crm_tasks(str(project_id))
