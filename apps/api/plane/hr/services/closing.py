# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Closing a month, and reopening one that has to be corrected.

A month goes open, submitted, approved, closed. Each step is somebody's decision
and is recorded as such, which is the entire reason for the sequence — the figures
themselves are already known long before anyone presses anything.

Closing does three things that matter. It freezes the totals onto the month, so
that what was agreed stays readable even if the records underneath later move. It
writes down what the figures were derived from — which contract, which schedule,
which absences — because a year later "why is March 148 hours" is a question
somebody will actually ask. And it stamps the records that fed into it, so they
refuse to be edited afterwards.

Reopening never returns a month to open. It goes to its own state and has to be
closed again, leaving both closings on the record. A correction that erased the
fact that the month had already been agreed would be the one thing nobody could
afterwards explain.
"""

# Django imports
from django.db import transaction
from django.utils import timezone

# Module imports
from plane.hr.models import (
    HrAbsence,
    HrAttendanceDay,
    HrAuditLog,
    HrContract,
    HrOpeningBalance,
    HrPeriod,
    HrPeriodDay,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.hr.services.ledger import has_running_timer, period_totals, rebuild_period
from plane.hr.utils.resolve import effective, effective_schedule


class TransitionRefused(Exception):
    """A move that the state of the month does not allow."""

    def __init__(self, message, conflict=True):
        super().__init__(message)
        self.message = message
        self.conflict = conflict


def _audit(period, actor, action, changes=None, reason=""):
    HrAuditLog.objects.create(
        workspace_id=period.workspace_id,
        profile_id=period.profile_id,
        actor=actor if actor is not None and not actor.is_anonymous else None,
        actor_email=getattr(actor, "email", "") or "",
        object_type="hr_period",
        object_id=period.id,
        action=action,
        changes=changes or {},
        reason=reason,
    )


def opening_balance_for(period):
    """Where this person's running balance stood when the month began.

    Taken from the previous month if that one has been closed, because its closing
    figure is already agreed. Otherwise from the balance recorded when the module
    started counting for this person — which is a number that was agreed with them
    rather than derived, and is the only honest starting point when there is no
    history to derive from.
    """
    # Only the month immediately before counts. Reaching further back for the most
    # recent closed month would step over one that was reopened, or never closed,
    # and silently drop whatever it contributed — an error that then rides forward
    # on every month after it.
    previous = (
        HrPeriod.objects.filter(
            profile_id=period.profile_id,
            period_start__lt=period.period_start,
        )
        .order_by("-period_start")
        .first()
    )
    if (
        previous is not None
        and previous.state == HrPeriod.State.LOCKED
        and previous.closing_balance_minutes is not None
    ):
        return previous.closing_balance_minutes

    balance = (
        HrOpeningBalance.objects.filter(
            profile_id=period.profile_id,
            kind=HrOpeningBalance.Kind.TIME_BALANCE,
            effective_on__lte=period.period_start,
            superseded_by__isnull=True,
        )
        .order_by("-effective_on")
        .first()
    )
    return balance.minutes if balance else 0


def _snapshot(period, totals):
    """What the figures were worked out from, kept so they can be explained later."""
    profile = period.profile
    contracts = list(HrContract.objects.filter(profile_id=profile.id))
    personal = list(HrWorkSchedule.objects.filter(profile_id=profile.id))
    defaults = list(
        HrWorkSchedule.objects.filter(profile__isnull=True)
    )
    contract = effective(contracts, period.period_start)
    schedule = effective_schedule(personal, defaults, period.period_start)

    days = HrPeriodDay.objects.filter(period_id=period.id).order_by("work_date")
    absences = HrAbsence.objects.filter(
        profile_id=profile.id,
        state=HrAbsence.State.APPROVED,
        start_date__lte=period.period_end,
        end_date__gte=period.period_start,
    ).values_list("id", flat=True)

    return {
        "timezone": profile.timezone or getattr(profile.workspace, "timezone", "") or "",
        "contract_id": str(contract.id) if contract else None,
        "schedule_id": str(schedule.id) if schedule else None,
        "holiday_calendar_id": str(profile.holiday_calendar_id) if profile.holiday_calendar_id else None,
        "absence_ids": [str(identifier) for identifier in absences],
        "records_target_hours": bool(contract.records_target_hours) if contract else False,
        "daily_target_minutes": {day.work_date.isoformat(): day.target_minutes for day in days},
        "totals": {key: value or 0 for key, value in totals.items()},
    }


@transaction.atomic
def submit(period, actor):
    """The person says their month is complete."""
    if period.state not in (HrPeriod.State.OPEN, HrPeriod.State.REOPENED):
        raise TransitionRefused("Only an open month can be submitted.")

    year, month = period.period_start.year, period.period_start.month
    if has_running_timer(period.profile, year, month):
        # An entry with no end has no length, so any total including it would be
        # out of date the moment it was read.
        raise TransitionRefused(
            "A timer is still running in this month. Stop it, then submit.", conflict=False
        )

    rebuild_period(period.profile, year, month, actor=actor)
    period.state = HrPeriod.State.SUBMITTED
    period.submitted_by = actor
    period.submitted_at = timezone.now()
    period.save()
    _audit(period, actor, "period_submitted")
    return period


@transaction.atomic
def approve(period, actor):
    """Somebody other than the person agrees the month is right."""
    if period.state != HrPeriod.State.SUBMITTED:
        raise TransitionRefused("Only a submitted month can be approved.")
    period.state = HrPeriod.State.APPROVED
    period.approved_by = actor
    period.approved_at = timezone.now()
    period.save()
    _audit(period, actor, "period_approved")
    return period


@transaction.atomic
def lock(period, actor):
    """Freeze the month.

    The final rebuild happens inside this transaction, so nothing can slip in
    between working the figures out and recording them.
    """
    if period.state != HrPeriod.State.APPROVED:
        raise TransitionRefused("Only an approved month can be closed.")

    year, month = period.period_start.year, period.period_start.month
    rebuild_period(period.profile, year, month, actor=actor)

    if HrPeriodDay.objects.filter(period_id=period.id, needs_review=True).exists():
        raise TransitionRefused(
            "Some days are marked for review because hours counted earlier are no "
            "longer there. Settle those before closing the month.",
            conflict=False,
        )

    totals = period_totals(period)
    opening = opening_balance_for(period)
    balance = totals["balance_minutes"] or 0
    # Time taken off in lieu already made its own day come out level, so without
    # taking it off the running balance the hours would be both credited and kept.
    consumed = totals["balance_consumed_minutes"] or 0

    period.target_minutes = totals["target_minutes"] or 0
    period.actual_minutes = totals["actual_minutes"] or 0
    period.balance_minutes = balance
    period.project_minutes = totals["project_minutes"] or 0
    period.non_project_minutes = totals["non_project_minutes"] or 0
    period.absence_minutes = totals["absence_minutes"] or 0
    period.holiday_minutes = totals["holiday_minutes"] or 0
    period.attendance_minutes = totals["attendance_minutes"] or 0
    period.leave_consumed_minutes = totals["leave_consumed_minutes"] or 0
    period.balance_consumed_minutes = consumed
    period.opening_balance_minutes = opening
    period.closing_balance_minutes = opening + balance - consumed

    # Carry forward any earlier closings. Assigning a fresh snapshot outright would
    # throw away the record reopen() kept of what the month was closed on the first
    # time, which is the one thing that makes a correction explicable afterwards.
    snapshot = _snapshot(period, totals)
    snapshot["superseded"] = (period.snapshot or {}).get("superseded", [])
    period.snapshot = snapshot
    period.state = HrPeriod.State.LOCKED
    period.locked_by = actor
    period.locked_at = timezone.now()
    period.save()

    _stamp_contributing_records(period)
    _audit(
        period,
        actor,
        "period_locked",
        changes={
            "target_minutes": period.target_minutes,
            "actual_minutes": period.actual_minutes,
            "balance_minutes": period.balance_minutes,
            "closing_balance_minutes": period.closing_balance_minutes,
        },
    )
    return period


def _stamp_contributing_records(period):
    """Mark what fed into a closed month, so those records refuse later edits."""
    scope = {"start": period.period_start, "end": period.period_end}
    HrAbsence.objects.filter(
        profile_id=period.profile_id,
        start_date__lte=scope["end"],
        end_date__gte=scope["start"],
        locked_period__isnull=True,
    ).update(locked_period=period)
    HrTimeEntry.objects.filter(
        profile_id=period.profile_id,
        entry_date__gte=scope["start"],
        entry_date__lte=scope["end"],
        locked_period__isnull=True,
    ).update(locked_period=period)
    HrAttendanceDay.objects.filter(
        profile_id=period.profile_id,
        work_date__gte=scope["start"],
        work_date__lte=scope["end"],
        locked_period__isnull=True,
    ).update(locked_period=period)


@transaction.atomic
def reopen(period, actor, reason):
    """Put a closed month back into play, without erasing that it was closed."""
    if period.state != HrPeriod.State.LOCKED:
        raise TransitionRefused("Only a closed month can be reopened.")
    if not (reason or "").strip():
        raise TransitionRefused("Say why the month is being reopened.", conflict=False)

    # The figures it was closed on are kept alongside the record of what it was
    # derived from, so the first closing stays readable after the second.
    snapshot = period.snapshot or {}
    superseded = snapshot.setdefault("superseded", [])
    superseded.append(
        {
            "locked_at": period.locked_at.isoformat() if period.locked_at else None,
            "target_minutes": period.target_minutes,
            "actual_minutes": period.actual_minutes,
            "balance_minutes": period.balance_minutes,
            "closing_balance_minutes": period.closing_balance_minutes,
            "reason": reason,
        }
    )

    period.snapshot = snapshot
    period.state = HrPeriod.State.REOPENED
    period.reopened_by = actor
    period.reopened_at = timezone.now()
    period.reopen_reason = reason
    period.save()

    _release_contributing_records(period)
    _audit(period, actor, "period_reopened", reason=reason)
    return period


def _release_contributing_records(period):
    """Let the records that fed a reopened month be edited again."""
    HrAbsence.objects.filter(locked_period=period).update(locked_period=None)
    HrTimeEntry.objects.filter(locked_period=period).update(locked_period=None)
    HrAttendanceDay.objects.filter(locked_period=period).update(locked_period=None)
