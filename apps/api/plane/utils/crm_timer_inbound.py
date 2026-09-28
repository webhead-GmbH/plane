# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Apply a timer started or stopped in the CRM to Plane.

Plane → CRM runs off the worklog signals. This is the other direction: the CRM
reports the timers its own users start and stop (its task view, its top-bar
timer) to Plane's timer webhook, and the reconciliation sweep reports the stops
the CRM makes without telling anyone. Both land here.

A timer Plane started never comes back as an event, because the CRM module
writes Plane's timers straight into its table and that fires none of the CRM's
hooks. So every event here is the CRM's own, and it is mirrored onto a worklog
tied to that CRM timer through ``CrmTimerLink`` — the same link Plane's own
timers use. That link is what stops the two directions from echoing: a CRM
timer that already has one is updated, never created again.
"""

# Python imports
import logging
from datetime import datetime, timezone

# Django imports
from django.db import transaction
from django.utils import timezone as dj_timezone

# Module imports
from plane.db.models import CrmTaskLink, CrmTimerLink, IssueWorkLog, ProjectMember, WorkspaceMember

logger = logging.getLogger("plane.worker")

TIMER_STARTED = "timer.started"
TIMER_STOPPED = "timer.stopped"
TIMER_EVENTS = (TIMER_STARTED, TIMER_STOPPED)


def _from_timestamp(value):
    """A CRM unix timestamp as an aware datetime, or None when there is none."""
    if value in (None, "", 0, "0"):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _seconds_between(start, end):
    """Whole seconds from start to end, never less than one — as Plane's own stop does.

    Counted between whole-second timestamps, as the CRM stores them: a timer Plane
    started has a fractional start, but its CRM copy starts at the whole second,
    so counting from the fraction would leave the two a second apart.
    """
    return max(int(end.timestamp()) - int(start.timestamp()), 1)


def plane_user_for_crm_staff(workspace_id, staff_id, staff_email):
    """The Plane user a CRM staff member is, or None.

    The reverse of how Plane picks a CRM staff id for its users: an explicit
    ``crm_staff_id`` on the membership wins, otherwise the email address has to
    match. A member explicitly mapped to a different CRM account is somebody else
    and is never matched by email.
    """
    members = WorkspaceMember.objects.filter(workspace_id=workspace_id, is_active=True).select_related("member")

    if staff_id:
        explicit = members.filter(crm_staff_id=staff_id).first()
        if explicit is not None:
            return explicit.member

    email = (staff_email or "").strip()
    if not email:
        return None
    by_email = members.filter(member__email__iexact=email).first()
    if by_email is None:
        return None
    if by_email.crm_staff_id and staff_id and by_email.crm_staff_id != staff_id:
        return None
    return by_email.member


def _mark_from_crm(worklog):
    """Keep this save from being mirrored back: it already is what the CRM holds."""
    worklog._crm_origin = True
    return worklog


def _stop_running(worklog, ended_at, note=None):
    """Close a running worklog at ``ended_at``; the CRM's note replaces an empty one."""
    worklog.duration = _seconds_between(worklog.started_at, ended_at)
    fields = ["duration", "updated_at"]
    if note:
        worklog.description = note
        fields.append("description")
    worklog.save(update_fields=fields)


def apply_crm_timer_event(integration, event, timer):
    """Mirror one CRM timer event onto Plane and say what was done.

    ``timer`` is the CRM's row: ``id``, ``task_id``, ``staff_id``, ``staff_email``,
    ``start_time`` and ``end_time`` (unix seconds, end empty while running) and
    ``note``. Anything that cannot or need not be mirrored is ignored with a
    reason rather than raised: the CRM cannot do anything useful with an error,
    and the same event may well arrive twice.
    """
    if event not in TIMER_EVENTS:
        return "ignored: unknown event"

    try:
        crm_timer_id = int(timer.get("id") or 0)
        crm_task_id = int(timer.get("task_id") or 0)
        staff_id = int(timer.get("staff_id") or 0)
    except (TypeError, ValueError):
        return "ignored: malformed timer"
    started_at = _from_timestamp(timer.get("start_time"))
    ended_at = _from_timestamp(timer.get("end_time"))
    note = (timer.get("note") or "").strip() or None

    if crm_timer_id <= 0 or crm_task_id <= 0 or started_at is None:
        return "ignored: malformed timer"
    if event == TIMER_STOPPED and ended_at is None:
        ended_at = dj_timezone.now()

    with transaction.atomic():
        link = (
            CrmTimerLink.objects.select_for_update()
            .filter(workspace_id=integration.workspace_id, crm_timer_id=crm_timer_id)
            .first()
        )
        if link is not None:
            return _apply_to_linked_worklog(link, event, ended_at, note)

        task_link = (
            CrmTaskLink.objects.filter(workspace_id=integration.workspace_id, crm_task_id=crm_task_id)
            .select_related("issue")
            .first()
        )
        if task_link is None:
            return "ignored: task not linked to a work item"
        issue = task_link.issue

        user = plane_user_for_crm_staff(integration.workspace_id, staff_id, timer.get("staff_email"))
        if user is None:
            return "ignored: no Plane member for this CRM staff member"
        if not ProjectMember.objects.filter(project_id=issue.project_id, member=user, is_active=True).exists():
            return "ignored: not a member of the work item's project"

        if ended_at is not None:
            return _record_finished_timer(integration, issue, user, crm_timer_id, started_at, ended_at, note)
        return _start_timer(integration, issue, user, crm_timer_id, started_at, note)


def _apply_to_linked_worklog(link, event, ended_at, note):
    """An event for a CRM timer Plane already mirrors."""
    worklog = IssueWorkLog.objects.select_for_update().filter(id=link.worklog_id).first()
    if worklog is None:
        return "ignored: the worklog was deleted in Plane"

    if event == TIMER_STARTED and ended_at is None:
        # A repeated delivery, or the start of a timer Plane itself put in the CRM.
        return "ignored: already running in Plane"

    if worklog.duration is not None:
        return "ignored: already stopped in Plane"

    _stop_running(_mark_from_crm(worklog), ended_at, note)
    link.last_synced_at = dj_timezone.now()
    link.save(update_fields=["last_synced_at", "updated_at"])
    return "stopped"


def _start_timer(integration, issue, user, crm_timer_id, started_at, note):
    """Start a Plane timer mirroring a CRM timer that was just started."""
    # One running timer per person, as when the timer is started in Plane: whatever
    # else is open stops where this one begins. Those saves are *not* marked as from
    # the CRM, so a stopped timer that has its own CRM counterpart is closed there
    # too — the CRM only does that itself when its auto-stop option is on.
    for running in IssueWorkLog.objects.select_for_update().filter(logged_by=user, duration__isnull=True):
        if running.started_at is None:
            continue
        _stop_running(running, max(started_at, running.started_at))

    worklog = _mark_from_crm(
        IssueWorkLog(
            workspace_id=integration.workspace_id,
            project_id=issue.project_id,
            issue=issue,
            logged_by=user,
            started_at=started_at,
            logged_at=started_at,
            duration=None,
            description=note,
            created_by=user,
            updated_by=user,
        )
    )
    worklog.save()
    CrmTimerLink.objects.create(
        workspace_id=integration.workspace_id,
        worklog=worklog,
        crm_timer_id=crm_timer_id,
        last_synced_at=dj_timezone.now(),
    )
    return "started"


def _record_finished_timer(integration, issue, user, crm_timer_id, started_at, ended_at, note):
    """Record a CRM timer whose start never reached Plane as a completed worklog.

    Its start predates this sync, or the delivery failed. Either way the hours are
    real and belong in Plane — unless they fall in a month already settled, which
    can no longer change.
    """
    from plane.hr.services.settled import settled_month_for

    if settled_month_for(user.id, started_at) is not None:
        return "ignored: the timer falls in a settled month"

    worklog = _mark_from_crm(
        IssueWorkLog(
            workspace_id=integration.workspace_id,
            project_id=issue.project_id,
            issue=issue,
            logged_by=user,
            started_at=started_at,
            logged_at=started_at,
            duration=_seconds_between(started_at, ended_at),
            description=note,
            created_by=user,
            updated_by=user,
        )
    )
    worklog.save()
    CrmTimerLink.objects.create(
        workspace_id=integration.workspace_id,
        worklog=worklog,
        crm_timer_id=crm_timer_id,
        last_synced_at=dj_timezone.now(),
    )
    return "recorded"
