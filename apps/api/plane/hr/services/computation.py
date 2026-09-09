# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Working out one person's figures for one day.

Deliberately free of database access, so the arithmetic can be exercised directly
against the cases that actually go wrong — a public holiday landing on a day
somebody does not work, a half day at the end of a range, a contract that changed
on the fifteenth.

Two conventions are settled here and should not be revisited casually, because
changing either alters every figure the module has ever produced:

The target is the contractual figure and nothing reduces it. Paid absence and
public holidays are added to the actual instead. The alternative — leaving the
actual as hours truly worked and shrinking the target — gives an identical
balance, but it means the "hours" column handed to payroll no longer contains the
hours the person is paid for. Each component is stored separately regardless, so a
report can present it either way without anything being recomputed.

Time worked is rounded once, per person per day per project, on the summed
seconds. Rounding each entry on its own would quietly lose most of a minute per
entry, which over a month of short entries is real money.
"""

# Python imports
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

FULL_DAY = 10
HALF_DAY = 20
HOURS = 30

MORNING = 10
AFTERNOON = 20

# Mirrors HrPeriodDay.DayKind, kept as plain integers so this module stays free of
# model imports.
KIND_WORKDAY = 10
KIND_NON_WORKING = 20
KIND_HOLIDAY = 30
KIND_HALF_HOLIDAY = 40
KIND_ABSENCE = 50
KIND_PARTIAL_ABSENCE = 60


def minutes_from_seconds(total_seconds):
    """Seconds to minutes, half rounded up. Applied once per bucket, never per row."""
    if not total_seconds:
        return 0
    return (int(total_seconds) + 30) // 60


def apply_fraction(minutes, fraction):
    """A fraction of a day's minutes, half rounded up rather than truncated."""
    if not minutes or fraction is None:
        return 0
    value = Decimal(minutes) * Decimal(fraction)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class AbsenceSlice:
    """One absence as it applies to a single day."""

    credits_actual: bool
    granularity: int = FULL_DAY
    # Which half, when this day is the first or last of a half-day range.
    half: int | None = None
    # Only for hour-granular absence.
    minutes: int | None = None
    consumes_leave: bool = False
    consumes_balance: bool = False
    # Lower wins where two absences cover the same day.
    precedence: int = 100


@dataclass
class DayInput:
    day: date
    # Whether a daily obligation is recorded for this person at all. Distinct from
    # a day whose obligation happens to be zero: a Saturday worked by somebody on a
    # weekday schedule is genuine surplus, whereas somebody who invoices their own
    # hours has no obligation to be above or below in the first place. Conflating
    # the two credits them the whole of every month as overtime.
    records_target: bool = True
    # What the contract says is owed on this day.
    scheduled_minutes: int = 0
    # What is credited when the person is paid but not working. Equal to the
    # scheduled minutes except under a flexitime agreement.
    credited_day_minutes: int = 0
    holiday_fraction: Decimal | None = None
    absences: list[AbsenceSlice] = field(default_factory=list)
    project_minutes: int = 0
    non_project_minutes: int = 0
    attendance_minutes: int | None = None


@dataclass
class DayResult:
    day: date
    target_minutes: int = 0
    project_minutes: int = 0
    non_project_minutes: int = 0
    absence_minutes: int = 0
    holiday_minutes: int = 0
    leave_minutes: int = 0
    balance_consumed_minutes: int = 0
    attendance_minutes: int | None = None
    actual_minutes: int = 0
    balance_minutes: int = 0
    day_kind: int = KIND_WORKDAY


def _half_day_minutes(remainder, half):
    """Half of a day's minutes, with an odd minute going to the morning.

    Arbitrary but fixed: somebody has to take the odd minute, and taking it
    consistently means a morning and an afternoon absence on the same day still add
    up to exactly one day.
    """
    if half == AFTERNOON:
        return remainder // 2
    return (remainder + 1) // 2


def compute_day(day_input):
    """Figures for one day."""
    result = DayResult(day=day_input.day)
    result.target_minutes = day_input.scheduled_minutes
    result.project_minutes = day_input.project_minutes
    result.non_project_minutes = day_input.non_project_minutes
    result.attendance_minutes = day_input.attendance_minutes

    credited_base = day_input.credited_day_minutes or day_input.scheduled_minutes

    # A public holiday is only worth anything on a day the person would have
    # worked. Someone who never works Mondays gains nothing from a Monday holiday,
    # and their target for that day was already nothing.
    if day_input.holiday_fraction is not None and credited_base:
        result.holiday_minutes = apply_fraction(credited_base, day_input.holiday_fraction)

    # Absence draws from what is left of the day after the holiday has taken its
    # share, so a half holiday and a half day of leave make one day rather than one
    # and a half.
    remainder = max(credited_base - result.holiday_minutes, 0)
    absence_total = 0
    # Where two absences cover the same day — sickness during booked leave being
    # the ordinary case — the one with the lower precedence number takes the day.
    for absence in sorted(day_input.absences, key=lambda item: item.precedence):
        if not absence.credits_actual:
            continue
        if absence.granularity == HOURS:
            share = min(absence.minutes or 0, remainder - absence_total)
        elif absence.granularity == HALF_DAY:
            # Half of the *day*, not half of what the holiday left. Someone taking
            # a half day of leave on a half holiday is off for the whole day, and
            # halving the remainder would leave them a quarter short and draw only
            # half as much from their leave as they actually spent. The cap below
            # is what stops the two adding to more than a day.
            share = min(_half_day_minutes(credited_base, absence.half), remainder - absence_total)
        else:
            share = remainder - absence_total
        share = max(share, 0)
        absence_total += share
        if absence.consumes_leave:
            result.leave_minutes += share
        if absence.consumes_balance:
            result.balance_consumed_minutes += share
        if absence_total >= remainder:
            break

    result.absence_minutes = absence_total
    result.actual_minutes = (
        result.project_minutes + result.non_project_minutes + result.absence_minutes + result.holiday_minutes
    )
    # No obligation, no surplus and no shortfall. Anything else accrues a balance
    # nobody agreed to and that grows by the whole of every month.
    result.balance_minutes = result.actual_minutes - result.target_minutes if day_input.records_target else 0
    result.day_kind = _classify(day_input, result)
    return result


def _classify(day_input, result):
    """A label for the day, for the benefit of anyone reading the breakdown.

    A day the person does not work is that first, whatever else falls on it — a
    public holiday on somebody's regular day off is not a holiday for them, and
    labelling it one invites the reader to expect hours that were never owed.
    """
    if not day_input.scheduled_minutes:
        return KIND_NON_WORKING
    if day_input.holiday_fraction is not None:
        if day_input.holiday_fraction < 1:
            # Half the day is a holiday; the other half may still be worked or
            # taken off, and the reader needs to be able to tell which.
            return KIND_PARTIAL_ABSENCE if result.absence_minutes else KIND_HALF_HOLIDAY
        return KIND_HOLIDAY
    if result.absence_minutes:
        if result.absence_minutes >= day_input.scheduled_minutes:
            return KIND_ABSENCE
        return KIND_PARTIAL_ABSENCE
    return KIND_WORKDAY


@dataclass
class PeriodTotals:
    target_minutes: int = 0
    actual_minutes: int = 0
    balance_minutes: int = 0
    project_minutes: int = 0
    non_project_minutes: int = 0
    absence_minutes: int = 0
    holiday_minutes: int = 0
    attendance_minutes: int = 0
    leave_consumed_minutes: int = 0
    balance_consumed_minutes: int = 0


def total_period(day_results):
    """Add a month of days up."""
    totals = PeriodTotals()
    for day in day_results:
        totals.target_minutes += day.target_minutes
        totals.actual_minutes += day.actual_minutes
        totals.balance_minutes += day.balance_minutes
        totals.project_minutes += day.project_minutes
        totals.non_project_minutes += day.non_project_minutes
        totals.absence_minutes += day.absence_minutes
        totals.holiday_minutes += day.holiday_minutes
        totals.attendance_minutes += day.attendance_minutes or 0
        totals.leave_consumed_minutes += day.leave_minutes
        totals.balance_consumed_minutes += day.balance_consumed_minutes
    return totals


def closing_balance(opening_minutes, totals):
    """Where the running balance stands after a month.

    Time taken off in lieu is subtracted separately, because crediting it to the
    actual already made the day come out level — without this the hours would be
    both credited and kept.
    """
    return opening_minutes + totals.balance_minutes - totals.balance_consumed_minutes
