# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Day and month boundaries, and the two days a year the clocks move.

The point of these is the difference between reading a timestamp in the declared
working timezone and reading it in UTC. Late-evening and early-morning entries are
where a month total silently goes wrong, so those are what is pinned here.
"""

# Python imports
import zoneinfo
from datetime import date, datetime, time

# Third-party imports
import pytest

# Module imports
from plane.hr.utils.calendar import (
    elapsed_minutes,
    hr_day_bounds_utc,
    hr_local_date,
    hr_month_bounds_utc,
    hr_timezone,
    is_nonexistent_local_time,
    iter_days,
    month_range,
)

pytestmark = pytest.mark.unit

VIENNA = "Europe/Vienna"
UTC = zoneinfo.ZoneInfo("UTC")


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class TestTimezoneResolution:
    def test_named_zone_wins(self):
        assert hr_timezone(VIENNA).key == VIENNA

    def test_unknown_zone_falls_back_rather_than_raising(self):
        # A bad value in one person's profile must not take a whole month's
        # figures down with it.
        assert hr_timezone("Mars/Olympus_Mons").key in {VIENNA, "UTC"}


class TestLocalDate:
    def test_late_evening_stays_on_its_own_day(self):
        # 23:30 in Vienna in winter is 22:30 UTC — same date either way.
        assert hr_local_date(utc(2026, 1, 15, 22, 30), VIENNA) == date(2026, 1, 15)

    def test_after_midnight_local_is_the_next_day_even_though_utc_disagrees(self):
        # 00:30 on the 16th in Vienna is still 23:30 on the 15th in UTC. Reading
        # this in UTC would file the work under the wrong day.
        assert hr_local_date(utc(2026, 1, 15, 23, 30), VIENNA) == date(2026, 1, 16)

    def test_summer_offset_is_two_hours(self):
        # 00:30 on 16 July in Vienna is 22:30 on the 15th in UTC.
        assert hr_local_date(utc(2026, 7, 15, 22, 30), VIENNA) == date(2026, 7, 16)

    def test_none_is_passed_through(self):
        assert hr_local_date(None, VIENNA) is None


class TestMonthBounds:
    def test_winter_month_starts_an_hour_before_midnight_utc(self):
        start, end = hr_month_bounds_utc(2026, 1, VIENNA)
        assert start == utc(2025, 12, 31, 23, 0)
        assert end == utc(2026, 1, 31, 23, 0)

    def test_summer_month_starts_two_hours_before(self):
        start, end = hr_month_bounds_utc(2026, 7, VIENNA)
        assert start == utc(2026, 6, 30, 22, 0)
        assert end == utc(2026, 7, 31, 22, 0)

    def test_december_rolls_into_january(self):
        start, end = hr_month_bounds_utc(2026, 12, VIENNA)
        assert start == utc(2026, 11, 30, 23, 0)
        assert end == utc(2026, 12, 31, 23, 0)

    def test_bounds_are_half_open_so_the_boundary_instant_belongs_to_one_month(self):
        _, january_end = hr_month_bounds_utc(2026, 1, VIENNA)
        february_start, _ = hr_month_bounds_utc(2026, 2, VIENNA)
        assert january_end == february_start

    def test_a_march_month_spans_the_clock_change_without_special_handling(self):
        # The clocks move on the last Sunday, never on the first of a month, so
        # both ends of March are unambiguous.
        start, end = hr_month_bounds_utc(2026, 3, VIENNA)
        assert start == utc(2026, 2, 28, 23, 0)
        assert end == utc(2026, 3, 31, 22, 0)

    def test_an_entry_just_after_midnight_falls_inside_the_new_month(self):
        start, _ = hr_month_bounds_utc(2026, 2, VIENNA)
        entry = utc(2026, 1, 31, 23, 30)  # 00:30 on 1 February in Vienna
        assert entry >= start
        assert hr_local_date(entry, VIENNA) == date(2026, 2, 1)


class TestDayBounds:
    def test_a_normal_day_is_twenty_four_hours(self):
        start, end = hr_day_bounds_utc(date(2026, 1, 15), VIENNA)
        assert (end - start).total_seconds() == 24 * 3600

    def test_the_spring_day_is_twenty_three_hours(self):
        start, end = hr_day_bounds_utc(date(2026, 3, 29), VIENNA)
        assert (end - start).total_seconds() == 23 * 3600

    def test_the_autumn_day_is_twenty_five_hours(self):
        start, end = hr_day_bounds_utc(date(2026, 10, 25), VIENNA)
        assert (end - start).total_seconds() == 25 * 3600


class TestElapsedAcrossClockChanges:
    def test_an_ordinary_shift(self):
        assert elapsed_minutes(date(2026, 1, 15), time(8, 0), time(16, 30), VIENNA) == 510

    def test_a_shift_over_the_autumn_change_is_an_hour_longer_than_the_clock_says(self):
        # 22:00 to 06:00 reads as eight hours on the clock but ten hours were
        # actually spent, because that night has an extra hour in it.
        minutes = elapsed_minutes(
            date(2026, 10, 24), time(22, 0), time(6, 0), VIENNA, crosses_midnight=True
        )
        assert minutes == 9 * 60

    def test_a_shift_over_the_spring_change_is_an_hour_shorter(self):
        minutes = elapsed_minutes(
            date(2026, 3, 28), time(22, 0), time(6, 0), VIENNA, crosses_midnight=True
        )
        assert minutes == 7 * 60

    def test_a_shift_not_crossing_midnight_stays_on_the_same_day(self):
        assert elapsed_minutes(date(2026, 6, 1), time(9, 15), time(17, 45), VIENNA) == 510


class TestNonexistentTimes:
    def test_a_time_the_clocks_jumped_over_is_flagged(self):
        # On the morning the clocks go forward, half past two never happens.
        assert is_nonexistent_local_time(date(2026, 3, 29), time(2, 30), VIENNA) is True

    def test_an_ordinary_time_is_not_flagged(self):
        assert is_nonexistent_local_time(date(2026, 3, 29), time(9, 0), VIENNA) is False

    def test_the_repeated_autumn_hour_is_not_flagged(self):
        # It happens twice rather than not at all, which is not an error.
        assert is_nonexistent_local_time(date(2026, 10, 25), time(2, 30), VIENNA) is False


class TestIteration:
    def test_month_range_covers_the_whole_month(self):
        first, last = month_range(2026, 2)
        assert first == date(2026, 2, 1)
        assert last == date(2026, 2, 28)

    def test_december_range_does_not_run_into_next_year(self):
        first, last = month_range(2026, 12)
        assert last == date(2026, 12, 31)

    def test_iter_days_is_inclusive_at_both_ends(self):
        days = list(iter_days(date(2026, 3, 1), date(2026, 3, 5)))
        assert len(days) == 5
        assert days[0] == date(2026, 3, 1)
        assert days[-1] == date(2026, 3, 5)

    def test_a_month_with_a_clock_change_still_has_its_full_count_of_days(self):
        first, last = month_range(2026, 3)
        assert len(list(iter_days(first, last))) == 31
