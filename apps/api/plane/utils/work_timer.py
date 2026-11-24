# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The rules for a timer on a work item, in one place.

The web app and connected apps both start and stop timers, and both must be refused
for the same reasons and in the same words: a timer is time somebody will be paid or
billed for, so two sets of rules that drift apart are two answers to "may I?". The
views decide *who is asking* (a session, a connected app's token) and whether that
person may touch the project at all; what a timer may and may not do is decided here.
"""

# Django imports
from django.db import IntegrityError
from django.utils import timezone

# Module imports
from plane.db.models import IssueAssignee, IssueWorkLog

_UNSET = object()


class TimerRefused(Exception):
    """A timer rule said no. `status` is the HTTP status the caller should answer with."""

    def __init__(self, message, *, status=400, reason=None):
        super().__init__(message)
        self.message = message
        self.status = status
        # A short code for callers that translate the message or branch on it.
        self.reason = reason


def allowed_state_groups(project):
    """Effective state groups on which a timer may run: the project's override, else the workspace default."""
    if project.worklog_timer_state_groups is not None:
        return project.worklog_timer_state_groups
    return project.workspace.worklog_timer_state_groups or ["started"]


def state_move_blocked_by_timer(issue, new_state):
    """Whether moving a work item to `new_state` would leave a timer running where time cannot be tracked.

    A running timer may only follow the work item into a state that also allows time
    tracking. Which groups those are is a workspace and project setting, so it is read
    rather than assumed: hard-coding "completed" both blocked moves between two perfectly
    legal states and let a timer run on in a state that forbids it.
    """
    if new_state is None or new_state.group in allowed_state_groups(issue.project):
        return False
    return IssueWorkLog.objects.filter(issue_id=issue.id, duration__isnull=True).exists()


def start_timer(user, issue):
    """Start `user`'s timer on a work item, ending any timer they already have running anywhere.

    Only an assignee may start one, and only while the work item is in a state that allows
    time tracking.
    """
    if not IssueAssignee.objects.filter(issue_id=issue.id, assignee=user).exists():
        raise TimerRefused("Only assignees of this issue can start the timer.", status=403, reason="not_assignee")

    if not issue.state or issue.state.group not in allowed_state_groups(issue.project):
        raise TimerRefused("A timer cannot be started on a work item in its current state.", reason="state_not_allowed")

    existing = IssueWorkLog.objects.filter(logged_by=user, duration__isnull=True).first()
    if existing:
        elapsed = int((timezone.now() - existing.started_at).total_seconds())
        existing.duration = max(elapsed, 1)
        existing.save(update_fields=["duration", "updated_at"])

    try:
        return IssueWorkLog.objects.create(
            workspace=issue.workspace,
            project_id=issue.project_id,
            issue_id=issue.id,
            logged_by=user,
            started_at=timezone.now(),
            logged_at=timezone.now(),
            duration=None,
            created_by=user,
            updated_by=user,
        )
    except IntegrityError:
        raise TimerRefused("A timer is already running for this issue.", reason="already_running")


def stop_timer(worklog, user, description=_UNSET):
    """End a running timer, and optionally set what the time was spent on."""
    elapsed = int((timezone.now() - worklog.started_at).total_seconds())
    worklog.duration = max(elapsed, 1)
    if description is not _UNSET:
        worklog.description = description or None
    worklog.updated_by = user
    worklog.save(update_fields=["duration", "description", "updated_by", "updated_at"])
    return worklog


NO_DESCRIPTION_CHANGE = _UNSET
