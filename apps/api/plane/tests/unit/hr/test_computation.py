# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The day arithmetic, exercised against the cases that go wrong in practice."""

# Python imports
from datetime import date
from decimal import Decimal

# Third-party imports
import pytest

# Module imports
from plane.hr.services.computation import (
    AFTERNOON,
    HALF_DAY,
    HOURS,
    KIND_ABSENCE,
    KIND_HALF_HOLIDAY,
    KIND_HOLIDAY,
    KIND_NON_WORKING,
    KIND_PARTIAL_ABSENCE,
    KIND_WORKDAY,
    MORNING,
    AbsenceSlice,
    DayInput,
    closing_balance,
    compute_day,
    minutes_from_seconds,
    total_period,
)

pytestmark = pytest.mark.unit

MONDAY = date(2026, 3, 2)
FULL = 462  # 7:42, a day of a 38.5 hour week over five days


def day(**kwargs):
    kwargs.setdefault("day", MONDAY)
    return DayInput(**kwargs)


class TestRounding:
    """Rounding happens once per bucket, on seconds, half up."""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(0, 0), (1, 0), (29, 0), (30, 1), (89, 1), (90, 2), (3600, 60), (3629, 60), (3630, 61)],
    )
    def test_half_rounds_up(self, seconds, expected):
        assert minutes_from_seconds(seconds) == expected

    def test_per_bucket_rounding_beats_per_row(self):
        # Forty entries of 59 seconds. Rounded per row they vanish entirely;
        # rounded once on the total they are the 39 minutes they actually are.
        rows = [59] * 40
        per_row = sum(minutes_from_seconds(value) for value in rows)
        per_bucket = minutes_from_seconds(sum(rows))
        assert per_row == 40
        assert per_bucket == 39


class TestPlainDays:
    def test_a_worked_day_balances(self):
        result = compute_day(day(scheduled_minutes=FULL, project_minutes=FULL))
        assert result.target_minutes == FULL
        assert result.actual_minutes == FULL
        assert result.balance_minutes == 0
        assert result.day_kind == KIND_WORKDAY

    def test_short_day_is_negative(self):
        result = compute_day(day(scheduled_minutes=FULL, project_minutes=400))
        assert result.balance_minutes == 400 - FULL

    def test_non_project_time_counts(self):
        result = compute_day(day(scheduled_minutes=FULL, project_minutes=300, non_project_minutes=162))
        assert result.actual_minutes == FULL
        assert result.balance_minutes == 0

    def test_a_day_off_the_schedule_is_not_a_shortfall(self):
        result = compute_day(day(scheduled_minutes=0))
        assert result.target_minutes == 0
        assert result.balance_minutes == 0
        assert result.day_kind == KIND_NON_WORKING

    def test_working_an_unscheduled_day_is_all_surplus(self):
        result = compute_day(day(scheduled_minutes=0, project_minutes=180))
        assert result.balance_minutes == 180


class TestHolidays:
    def test_holiday_credits_the_scheduled_day(self):
        result = compute_day(day(scheduled_minutes=FULL, holiday_fraction=Decimal("1.00")))
        assert result.holiday_minutes == FULL
        assert result.actual_minutes == FULL
        assert result.balance_minutes == 0
        assert result.day_kind == KIND_HOLIDAY

    def test_part_timer_gains_nothing_from_a_holiday_they_do_not_work(self):
        # The case that is most often got backwards. Somebody who never works
        # Mondays is owed nothing for a Monday holiday, and their target for that
        # day was already nothing — so the day is simply neutral.
        result = compute_day(day(scheduled_minutes=0, holiday_fraction=Decimal("1.00")))
        assert result.holiday_minutes == 0
        assert result.target_minutes == 0
        assert result.balance_minutes == 0

    def test_half_holiday_credits_half(self):
        result = compute_day(day(scheduled_minutes=FULL, holiday_fraction=Decimal("0.50")))
        assert result.holiday_minutes == 231
        assert result.balance_minutes == 231 - FULL
        assert result.day_kind == KIND_HALF_HOLIDAY

    def test_half_holiday_plus_half_worked_balances(self):
        result = compute_day(
            day(scheduled_minutes=FULL, holiday_fraction=Decimal("0.50"), project_minutes=231)
        )
        assert result.balance_minutes == 0

    def test_odd_minute_rounds_up_not_away(self):
        result = compute_day(day(scheduled_minutes=463, holiday_fraction=Decimal("0.50")))
        assert result.holiday_minutes == 232


class TestAbsence:
    def test_full_day_leave_covers_the_day(self):
        result = compute_day(
            day(
                scheduled_minutes=FULL,
                absences=[AbsenceSlice(credits_actual=True, consumes_leave=True)],
            )
        )
        assert result.absence_minutes == FULL
        assert result.leave_minutes == FULL
        assert result.balance_minutes == 0
        assert result.day_kind == KIND_ABSENCE

    def test_unpaid_absence_credits_nothing(self):
        result = compute_day(
            day(scheduled_minutes=FULL, absences=[AbsenceSlice(credits_actual=False)])
        )
        assert result.absence_minutes == 0
        assert result.balance_minutes == -FULL

    def test_half_day_leave_plus_half_worked_balances(self):
        result = compute_day(
            day(
                scheduled_minutes=FULL,
                project_minutes=231,
                absences=[AbsenceSlice(credits_actual=True, granularity=HALF_DAY, half=AFTERNOON)],
            )
        )
        assert result.absence_minutes == 231
        assert result.balance_minutes == 0
        assert result.day_kind == KIND_PARTIAL_ABSENCE

    def test_two_halves_make_exactly_one_day_when_minutes_are_odd(self):
        # The odd minute goes to the morning, so the two halves still add to the
        # whole rather than leaving a stray minute.
        result = compute_day(
            day(
                scheduled_minutes=463,
                absences=[
                    AbsenceSlice(credits_actual=True, granularity=HALF_DAY, half=MORNING),
                    AbsenceSlice(credits_actual=True, granularity=HALF_DAY, half=AFTERNOON),
                ],
            )
        )
        assert result.absence_minutes == 463
        assert result.balance_minutes == 0

    def test_hour_granular_absence(self):
        result = compute_day(
            day(
                scheduled_minutes=FULL,
                project_minutes=342,
                absences=[AbsenceSlice(credits_actual=True, granularity=HOURS, minutes=120)],
            )
        )
        assert result.absence_minutes == 120
        assert result.balance_minutes == 0

    def test_absence_cannot_credit_more_than_the_day_holds(self):
        result = compute_day(
            day(
                scheduled_minutes=FULL,
                absences=[AbsenceSlice(credits_actual=True, granularity=HOURS, minutes=900)],
            )
        )
        assert result.absence_minutes == FULL

    def test_holiday_and_absence_on_one_day_do_not_double_count(self):
        # A half holiday and leave for the rest of the day is one day, not one and
        # a half.
        result = compute_day(
            day(
                scheduled_minutes=FULL,
                holiday_fraction=Decimal("0.50"),
                absences=[AbsenceSlice(credits_actual=True, consumes_leave=True)],
            )
        )
        assert result.holiday_minutes == 231
        assert result.absence_minutes == FULL - 231
        assert result.actual_minutes == FULL
        assert result.balance_minutes == 0

    def test_time_off_in_lieu_is_tracked_separately_from_leave(self):
        result = compute_day(
            day(
                scheduled_minutes=FULL,
                absences=[AbsenceSlice(credits_actual=True, consumes_balance=True)],
            )
        )
        assert result.leave_minutes == 0
        assert result.balance_consumed_minutes == FULL


class TestHalfDayOnAHalfHoliday:
    """The combination that was getting three quarters of a day instead of one."""

    def test_a_half_day_of_leave_on_a_half_holiday_covers_the_whole_day(self):
        # 24 December is half a holiday; the person takes leave for the working
        # half. They are off all day, so the day must come out level — and their
        # leave account must lose the half they actually spent, not half of what
        # the holiday left.
        result = compute_day(
            day(
                scheduled_minutes=FULL,
                holiday_fraction=Decimal("0.50"),
                absences=[
                    AbsenceSlice(
                        credits_actual=True,
                        granularity=HALF_DAY,
                        half=MORNING,
                        consumes_leave=True,
                    )
                ],
            )
        )
        assert result.holiday_minutes == 231
        assert result.absence_minutes == 231
        assert result.leave_minutes == 231
        assert result.actual_minutes == FULL
        assert result.balance_minutes == 0

    def test_a_half_day_still_cannot_exceed_what_the_day_has_left(self):
        # A full holiday leaves nothing for an absence to draw on.
        result = compute_day(
            day(
                scheduled_minutes=FULL,
                holiday_fraction=Decimal("1.00"),
                absences=[AbsenceSlice(credits_actual=True, granularity=HALF_DAY, half=MORNING)],
            )
        )
        assert result.holiday_minutes == FULL
        assert result.absence_minutes == 0
        assert result.actual_minutes == FULL


class TestOverlappingAbsences:
    def test_the_lower_precedence_number_takes_the_day(self):
        # Sickness during booked leave: the day is charged to sickness, and the
        # leave stays in the account. Which record was entered first is not a rule
        # anybody could explain to the person whose leave was spent.
        sick = AbsenceSlice(credits_actual=True, precedence=10)
        leave = AbsenceSlice(credits_actual=True, consumes_leave=True, precedence=100)
        result = compute_day(day(scheduled_minutes=FULL, absences=[leave, sick]))
        assert result.absence_minutes == FULL
        assert result.leave_minutes == 0

    def test_order_of_entry_does_not_change_the_outcome(self):
        sick = AbsenceSlice(credits_actual=True, precedence=10)
        leave = AbsenceSlice(credits_actual=True, consumes_leave=True, precedence=100)
        first = compute_day(day(scheduled_minutes=FULL, absences=[sick, leave]))
        second = compute_day(day(scheduled_minutes=FULL, absences=[leave, sick]))
        assert first.leave_minutes == second.leave_minutes == 0


class TestDayLabels:
    def test_a_holiday_on_a_day_off_is_labelled_a_day_off(self):
        # Calling it a holiday would invite the reader to expect hours that were
        # never owed.
        result = compute_day(day(scheduled_minutes=0, holiday_fraction=Decimal("1.00")))
        assert result.day_kind == KIND_NON_WORKING

    def test_a_half_holiday_with_leave_shows_as_partly_absent(self):
        result = compute_day(
            day(
                scheduled_minutes=FULL,
                holiday_fraction=Decimal("0.50"),
                absences=[AbsenceSlice(credits_actual=True, granularity=HALF_DAY, half=MORNING)],
            )
        )
        assert result.day_kind == KIND_PARTIAL_ABSENCE

    def test_a_plain_half_holiday_still_reads_as_one(self):
        result = compute_day(day(scheduled_minutes=FULL, holiday_fraction=Decimal("0.50")))
        assert result.day_kind == KIND_HALF_HOLIDAY


class TestFlexitime:
    def test_notional_day_is_credited_rather_than_the_schedule(self):
        # Under a flexitime agreement the daily distribution is the person's own,
        # so an absence is credited the agreed notional day, not whatever the
        # schedule happens to say for that weekday.
        result = compute_day(
            day(
                scheduled_minutes=600,
                credited_day_minutes=462,
                absences=[AbsenceSlice(credits_actual=True, consumes_leave=True)],
            )
        )
        assert result.absence_minutes == 462
        assert result.target_minutes == 600
        assert result.balance_minutes == 462 - 600


class TestPeriodTotals:
    def test_totals_add_up(self):
        days = [
            compute_day(day(day=date(2026, 3, 2), scheduled_minutes=FULL, project_minutes=FULL)),
            compute_day(day(day=date(2026, 3, 3), scheduled_minutes=FULL, project_minutes=400)),
            compute_day(day(day=date(2026, 3, 7), scheduled_minutes=0)),
        ]
        totals = total_period(days)
        assert totals.target_minutes == FULL * 2
        assert totals.actual_minutes == FULL + 400
        assert totals.balance_minutes == 400 - FULL

    def test_time_off_in_lieu_is_deducted_from_the_running_balance(self):
        # Taking a day in lieu leaves the day itself level, so without deducting it
        # explicitly the hours would be both credited and kept.
        days = [
            compute_day(
                day(
                    scheduled_minutes=FULL,
                    absences=[AbsenceSlice(credits_actual=True, consumes_balance=True)],
                )
            )
        ]
        totals = total_period(days)
        assert totals.balance_minutes == 0
        assert closing_balance(1000, totals) == 1000 - FULL
