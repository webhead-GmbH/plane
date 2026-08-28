# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Closing timers that were left running.

A timer is only stopped automatically when the same person starts another one, so
one left going on a Friday evening runs all weekend and writes the whole weekend
into the month. It also blocks that person on Monday, because only one timer per
person may be open at a time — so the fault gets in the way of the work as well as
the figures.

The sweep closes them at a plausible ceiling rather than at the elapsed time, and
says so on the entry. Guessing the real figure would be worse than admitting there
isn't one: only the person who was there knows when they stopped, and they can
correct it through the ordinary edit.
"""

# Python imports
import logging
from datetime import timedelta

# Django imports
from django.conf import settings
from django.utils import timezone

# Third-party imports
from celery import shared_task

# Module imports
from plane.db.models import IssueWorkLog
from plane.hr.conf import DEFAULT_MAX_TIMER_MINUTES
from plane.hr.models import HrAuditLog, HrEmploymentProfile
from plane.utils.exception_logger import log_exception

logger = logging.getLogger("plane.worker")

AUTO_STOPPED_PREFIX = "[automatically stopped]"


@shared_task
def close_runaway_timers():
    """Close any timer that has been running longer than a working day could be."""
    cap_minutes = int(getattr(settings, "HR_MAX_TIMER_MINUTES", DEFAULT_MAX_TIMER_MINUTES))
    cutoff = timezone.now() - timedelta(minutes=cap_minutes)

    stale = IssueWorkLog.objects.filter(
        duration__isnull=True,
        started_at__isnull=False,
        started_at__lt=cutoff,
    ).select_related("workspace")

    closed = 0
    for worklog in stale:
        try:
            elapsed = int((timezone.now() - worklog.started_at).total_seconds())
            worklog.duration = cap_minutes * 60
            note = worklog.description or ""
            if not note.startswith(AUTO_STOPPED_PREFIX):
                worklog.description = f"{AUTO_STOPPED_PREFIX} {note}".strip()
            # Saved one at a time on purpose. A bulk update would skip the signals,
            # and the CRM genuinely needs to learn that this timer ended — it has
            # been sitting open over there too.
            worklog.save()
            _record(worklog, elapsed, cap_minutes * 60)
            closed += 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the sweep
            log_exception(exc)

    if closed:
        logger.info("Closed %s timer(s) left running beyond %s minutes", closed, cap_minutes)
    return closed


def _record(worklog, elapsed_seconds, capped_seconds):
    """Write down that this was closed by the system and not by the person."""
    profile = HrEmploymentProfile.objects.filter(
        workspace_id=worklog.workspace_id, member_id=worklog.logged_by_id
    ).first()
    if profile is None:
        # Somebody outside the HR module logged the time. The timer still had to be
        # closed, but there is no employment record to hang the note on.
        return

    HrAuditLog.objects.create(
        workspace_id=worklog.workspace_id,
        profile_id=profile.id,
        actor=None,
        actor_email="",
        object_type="issue_work_log",
        object_id=worklog.id,
        action="timer_automatically_stopped",
        changes={
            "elapsed_seconds": elapsed_seconds,
            "recorded_seconds": capped_seconds,
            "started_at": worklog.started_at.isoformat() if worklog.started_at else None,
        },
        reason=(
            "The timer was left running past the point where it could still be a "
            "working day. It has been closed at the maximum and needs correcting by "
            "the person who logged it."
        ),
    )
