# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rebuilding one person's month, day by day.

The rebuild is idempotent: it reads the sources, works out every day from
scratch, and writes the result over whatever was there. Nothing is merged, so it
does not matter how many times it runs or in what order, and a day that has gone
wrong is repaired simply by running it again.

It also does one thing that reading the sources on demand could never do. Each day
remembers the identifiers of the entries it counted, so the next rebuild can see
that something it counted before is no longer there. That happens more easily than
it sounds: deleting a work item takes every timer on it, including other people's,
and the rows disappear from view with nothing recorded anywhere. Rather than let
the month quietly shrink, the day is flagged and the discrepancy written down,
because whether those hours were withdrawn on purpose or lost by accident is not a
question the remaining data can answer.

A month that has been closed is left alone entirely. That is the whole of what
closing means here — the rebuild stops touching it — which is why the same table
serves both the live view and the frozen record.
"""

# Python imports
from collections import defaultdict

# Django imports
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone

# Module imports
from plane.db.models import IssueWorkLog
from plane.hr.models import (
    HrAbsence,
    HrAttendanceDay,
    HrAuditLog,
    HrContract,
    HrHoliday,
    HrHolidayCalendar,
    HrPeriod,
    HrPeriodDay,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.hr.services.computation import (
    FULL_DAY,
    HALF_DAY,
    HOURS,
    AbsenceSlice,
    DayInput,
    compute_day,
    minutes_from_seconds,
)
from plane.hr.utils.calendar import (
    hr_local_date,
    hr_month_bounds_utc,
    iter_days,
    month_range,
)
from plane.hr.utils.resolve import (
    AbsenceLookup,
    HolidayLookup,
    credited_day_minutes,
    effective,
    effective_schedule,
    scheduled_minutes,
)


def _profile_timezone(profile):
    """The zone this person's days are measured in."""
    return profile.timezone or getattr(profile.workspace, "timezone", "") or None


def _slice_for_day(absence, day, absence_type, records_leave_account=True):
    """How one absence applies to one particular day of its range."""
    granularity = absence.granularity
    half = None
    if granularity == HALF_DAY:
        # Half days only mean anything at the ends of a range; the days in between
        # are whole ones. A one-day absence is both ends at once, and the opening
        # half is the one that describes it.
        if day == absence.start_date:
            half = absence.start_half
        elif day == absence.end_date:
            half = absence.end_half
        else:
            granularity = FULL_DAY

    # Somebody with no leave account cannot spend leave they do not have, so an
    # absence that would draw on one credits nothing for them. Absences that draw
    # on neither account — sickness, for instance — are unaffected.
    consumes_leave = absence_type.consumes_leave_entitlement
    credits_actual = absence_type.credits_actual
    if consumes_leave and not records_leave_account:
        credits_actual = False

    return AbsenceSlice(
        credits_actual=credits_actual,
        granularity=granularity,
        half=half,
        minutes=absence.minutes_per_day if granularity == HOURS else None,
        consumes_leave=consumes_leave and records_leave_account,
        consumes_balance=absence_type.consumes_balance,
        precedence=absence_type.precedence,
    )


def _worklog_minutes_by_day(profile, first, last, tz):
    """Hours logged against work items, bucketed by day and rounded once each.

    Rounding is applied per day and per project rather than per entry, because a
    truncated entry loses up to a minute and a month of short entries loses a
    great deal more than that.
    """
    lo, hi = hr_month_bounds_utc(first.year, first.month, tz)
    rows = (
        IssueWorkLog.objects.filter(
            logged_by_id=profile.member_id,
            workspace_id=profile.workspace_id,
            # A running timer has no length yet, so it is not counted. It is
            # surfaced separately rather than guessed at.
            duration__isnull=False,
        )
        .annotate(occurred=Coalesce("started_at", "logged_at"))
        .filter(occurred__gte=lo, occurred__lt=hi)
        .values("id", "occurred", "duration", "project_id")
    )

    seconds_by_bucket = defaultdict(int)
    ids_by_day = defaultdict(list)
    for row in rows:
        day = hr_local_date(row["occurred"], tz)
        if day is None or day < first or day > last:
            continue
        seconds_by_bucket[(day, row["project_id"])] += row["duration"] or 0
        ids_by_day[day].append(row["id"])

    minutes_by_day = defaultdict(int)
    for (day, _project_id), seconds in seconds_by_bucket.items():
        minutes_by_day[day] += minutes_from_seconds(seconds)
    return minutes_by_day, ids_by_day


def _time_entry_minutes_by_day(profile, first, last):
    rows = HrTimeEntry.objects.filter(
        profile_id=profile.id,
        entry_date__gte=first,
        entry_date__lte=last,
    ).values("id", "entry_date", "minutes")

    minutes_by_day = defaultdict(int)
    ids_by_day = defaultdict(list)
    for row in rows:
        minutes_by_day[row["entry_date"]] += row["minutes"]
        ids_by_day[row["entry_date"]].append(row["id"])
    return minutes_by_day, ids_by_day


def _attendance_by_day(profile, first, last):
    rows = HrAttendanceDay.objects.filter(
        profile_id=profile.id,
        work_date__gte=first,
        work_date__lte=last,
    ).values("work_date", "net_minutes")
    return {row["work_date"]: row["net_minutes"] for row in rows}


def _holiday_lookup(profile, first, last):
    calendar_id = profile.holiday_calendar_id
    if calendar_id is None:
        default = (
            HrHolidayCalendar.objects.filter(workspace_id=profile.workspace_id, is_default=True)
            .values_list("id", flat=True)
            .first()
        )
        calendar_id = default
    if calendar_id is None:
        return HolidayLookup([])
    holidays = HrHoliday.objects.filter(
        calendar_id=calendar_id,
        date__gte=first,
        date__lte=last,
    )
    return HolidayLookup(list(holidays))


def _absence_lookup(profile, first, last):
    absences = (
        HrAbsence.objects.filter(
            profile_id=profile.id,
            state=HrAbsence.State.APPROVED,
            start_date__lte=last,
            end_date__gte=first,
        )
        .select_related("absence_type")
        .order_by("start_date")
    )
    return AbsenceLookup(list(absences))


def _records_disappeared(previous_ids, current_ids):
    """Identifiers counted last time that are nowhere in the month now.

    Compared across the whole month rather than day by day, because moving an
    entry to a different date within the same month is a correction, not a loss —
    a per-day comparison would report it as hours having vanished from the day it
    left and flag a month that is entirely intact.
    """
    if not previous_ids:
        return []
    current = {str(identifier) for identifier in current_ids}
    return [identifier for identifier in previous_ids if str(identifier) not in current]


@transaction.atomic
def rebuild_period(profile, year, month, actor=None):
    """Recompute one person's month. Returns the period, or None if it is closed."""
    first, last = month_range(year, month)
    HrPeriod.objects.get_or_create(
        profile_id=profile.id,
        period_start=first,
        defaults={"workspace_id": profile.workspace_id, "period_end": last},
    )
    # Re-read under a row lock. Two rebuilds of the same month can otherwise both
    # find no days and both try to create them, and the second loses on the unique
    # constraint — which at this size is unlikely but produces a 500 in a request
    # that had nothing wrong with it.
    period = HrPeriod.objects.select_for_update().get(profile_id=profile.id, period_start=first)

    # Only a month still in play is rebuilt. A closed one is closed, and a
    # submitted or approved one has figures somebody has already looked at —
    # rewriting those underneath them, on a passing GET, would mean approving one
    # set of numbers and locking another.
    if period.state not in (HrPeriod.State.OPEN, HrPeriod.State.REOPENED):
        return None

    tz = _profile_timezone(profile)

    contracts = list(HrContract.objects.filter(profile_id=profile.id))
    personal_schedules = list(HrWorkSchedule.objects.filter(profile_id=profile.id))
    default_schedules = list(
        HrWorkSchedule.objects.filter(workspace_id=profile.workspace_id, profile__isnull=True)
    )
    holidays = _holiday_lookup(profile, first, last)
    absences = _absence_lookup(profile, first, last)

    project_minutes, worklog_ids = _worklog_minutes_by_day(profile, first, last, tz)
    entry_minutes, entry_ids = _time_entry_minutes_by_day(profile, first, last)
    attendance = _attendance_by_day(profile, first, last)

    existing = {row.work_date: row for row in HrPeriodDay.objects.filter(period_id=period.id)}

    # Compared across the month as a whole: an entry moved to another date is a
    # correction, not a loss.
    seen_before = {
        str(identifier) for row in existing.values() for identifier in (row.worklog_ids or [])
    }
    seen_now = {str(identifier) for ids in worklog_ids.values() for identifier in ids}
    vanished = seen_before - seen_now

    to_create = []
    to_update = []
    disappearances = []

    for day in iter_days(first, last):
        contract = effective(contracts, day)
        # Whether a daily obligation is recorded, and whether the person has a
        # leave account at all, are separate per-contract decisions. For the
        # self-invoicing arrangements the first is deliberately off, which must not
        # silently switch off the second.
        records_target = contract.records_target_hours if contract else False
        records_leave = contract.records_leave_account if contract else False
        schedule = effective_schedule(personal_schedules, default_schedules, day)

        holiday = holidays.get(day)
        slices = [
            _slice_for_day(absence, day, absence.absence_type, records_leave_account=records_leave)
            for absence in absences.covering(day)
        ]

        day_input = DayInput(
            day=day,
            scheduled_minutes=scheduled_minutes(schedule, day) if records_target else 0,
            # The notional day stays available as the base for crediting an
            # absence even where no target is recorded, so a person with a leave
            # account still has their leave measured against a real day.
            credited_day_minutes=credited_day_minutes(schedule, day),
            # Holiday pay belongs with a recorded working obligation. Somebody
            # invoicing their own hours is not owed a public holiday.
            holiday_fraction=holiday.day_fraction if (holiday and records_target) else None,
            absences=slices,
            project_minutes=project_minutes.get(day, 0),
            non_project_minutes=entry_minutes.get(day, 0),
            attendance_minutes=attendance.get(day),
        )
        result = compute_day(day_input)

        current_worklog_ids = worklog_ids.get(day, [])
        row = existing.get(day)
        gone = [
            identifier
            for identifier in (row.worklog_ids or [] if row else [])
            if str(identifier) in vanished
        ]
        if gone:
            disappearances.append((day, gone))

        values = {
            "workspace_id": profile.workspace_id,
            "profile_id": profile.id,
            "target_minutes": result.target_minutes,
            "project_minutes": result.project_minutes,
            "non_project_minutes": result.non_project_minutes,
            "attendance_minutes": result.attendance_minutes,
            "absence_minutes": result.absence_minutes,
            "holiday_minutes": result.holiday_minutes,
            "actual_minutes": result.actual_minutes,
            "balance_minutes": result.balance_minutes,
            "leave_minutes": result.leave_minutes,
            "balance_consumed_minutes": result.balance_consumed_minutes,
            "day_kind": result.day_kind,
            "worklog_ids": current_worklog_ids,
            "time_entry_ids": entry_ids.get(day, []),
            "last_rebuilt_at": timezone.now(),
            # Once raised the flag stays until somebody settles it. Clearing it on
            # the next rebuild would be worse than leaving it: the discrepancy
            # would come and go before anyone had a chance to look, and the point
            # of raising it is that a person has to decide what it meant.
            "needs_review": bool(gone) or bool(row.needs_review if row else False),
        }

        if row is None:
            to_create.append(HrPeriodDay(period_id=period.id, work_date=day, **values))
        else:
            for name, value in values.items():
                setattr(row, name, value)
            to_update.append(row)

    if to_create:
        HrPeriodDay.objects.bulk_create(to_create, batch_size=100)
    if to_update:
        HrPeriodDay.objects.bulk_update(
            to_update,
            [
                "target_minutes",
                "project_minutes",
                "non_project_minutes",
                "attendance_minutes",
                "absence_minutes",
                "holiday_minutes",
                "actual_minutes",
                "balance_minutes",
                "leave_minutes",
                "balance_consumed_minutes",
                "day_kind",
                "worklog_ids",
                "time_entry_ids",
                "last_rebuilt_at",
                "needs_review",
                "updated_at",
            ],
            batch_size=100,
        )

    _record_disappearances(profile, period, disappearances, actor)
    return period


def _record_disappearances(profile, period, disappearances, actor):
    """Write down hours that were counted before and are not there now."""
    if not disappearances:
        return
    entries = [
        HrAuditLog(
            workspace_id=profile.workspace_id,
            profile_id=profile.id,
            actor=actor if actor and not actor.is_anonymous else None,
            actor_email=getattr(actor, "email", "") or "",
            object_type="hr_period_day",
            action="counted_hours_disappeared",
            changes={
                "date": day.isoformat(),
                "period": str(period.id),
                "missing_worklog_ids": [str(identifier) for identifier in gone],
            },
            reason=(
                "Entries counted by a previous rebuild are no longer present. "
                "They may have been withdrawn deliberately or removed along with "
                "a work item; the day has been marked for review."
            ),
        )
        for day, gone in disappearances
    ]
    HrAuditLog.objects.bulk_create(entries, batch_size=100)


def settle_day(day, actor, note):
    """Record that somebody has looked at a flagged day and decided what it meant.

    The flag exists because hours counted earlier are no longer there, and only a
    person can say whether they were withdrawn on purpose or lost by accident.
    Settling does not change any figure — it records that the question was asked
    and answered, which is what lets the month be closed.
    """
    if not (note or "").strip():
        raise ValueError("Say what was decided about this day.")

    day.needs_review = False
    day.note = note
    day.save()

    HrAuditLog.objects.create(
        workspace_id=day.workspace_id,
        profile_id=day.profile_id,
        actor=actor if actor is not None and not actor.is_anonymous else None,
        actor_email=getattr(actor, "email", "") or "",
        object_type="hr_period_day",
        object_id=day.id,
        action="review_settled",
        changes={"date": day.work_date.isoformat()},
        reason=note,
    )
    return day


def period_totals(period):
    """Totals for a month, summed from its days.

    Kept out of the period row while the month is open so there is only ever one
    place a figure comes from. They are frozen onto the row when it is closed.
    """
    from django.db.models import Sum

    return HrPeriodDay.objects.filter(period_id=period.id).aggregate(
        target_minutes=Sum("target_minutes"),
        actual_minutes=Sum("actual_minutes"),
        balance_minutes=Sum("balance_minutes"),
        project_minutes=Sum("project_minutes"),
        non_project_minutes=Sum("non_project_minutes"),
        absence_minutes=Sum("absence_minutes"),
        holiday_minutes=Sum("holiday_minutes"),
        attendance_minutes=Sum("attendance_minutes"),
        leave_consumed_minutes=Sum("leave_minutes"),
        balance_consumed_minutes=Sum("balance_consumed_minutes"),
    )


def has_running_timer(profile, year, month):
    """Whether a timer is still going in this month.

    A month cannot be submitted while one is, because the entry has no length yet
    and any figure including it would be out of date the moment it was read.
    """
    tz = _profile_timezone(profile)
    lo, hi = hr_month_bounds_utc(year, month, tz)
    return (
        IssueWorkLog.objects.filter(
            logged_by_id=profile.member_id,
            workspace_id=profile.workspace_id,
            duration__isnull=True,
        )
        .annotate(occurred=Coalesce("started_at", F("logged_at")))
        .filter(occurred__gte=lo, occurred__lt=hi)
        .exists()
    )
