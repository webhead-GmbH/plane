# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""How long somebody was at work, including the two days a year the clock lies."""

# Python imports
from datetime import date, time
from types import SimpleNamespace

# Module imports
from plane.hr.services.attendance import net_minutes_for, problem_with


def day(
    work_date=date(2026, 3, 2),
    started=time(9, 0),
    ended=time(17, 0),
    breaks=30,
    tz="Europe/Vienna",
    crosses_midnight=False,
):
    return SimpleNamespace(
        work_date=work_date,
        started_at_local=started,
        ended_at_local=ended,
        break_minutes=breaks,
        local_timezone=tz,
        crosses_midnight=crosses_midnight,
    )


class TestNetMinutes:
    def test_an_ordinary_day_is_the_clock_less_the_breaks(self):
        assert net_minutes_for(day()) == 8 * 60 - 30

    def test_a_day_still_running_has_no_total_yet(self):
        """Reading a guess off the current time would change the figure each time."""
        assert net_minutes_for(day(ended=None)) == 0

    def test_the_night_the_clocks_go_back_is_an_hour_longer(self):
        """Vienna, 25 October 2026: 03:00 happens twice, so this shift is eleven hours.

        Subtracting the wall-clock readings would say ten, and the person would be
        an hour short for work they did.
        """
        assert net_minutes_for(
            day(work_date=date(2026, 10, 24), started=time(20, 0), ended=time(6, 0), breaks=0, crosses_midnight=True)
        ) == 11 * 60

    def test_the_night_the_clocks_go_forward_is_an_hour_shorter(self):
        """Vienna, 29 March 2026: 02:00 to 03:00 never happens, so this is nine."""
        assert net_minutes_for(
            day(work_date=date(2026, 3, 28), started=time(20, 0), ended=time(6, 0), breaks=0, crosses_midnight=True)
        ) == 9 * 60

    def test_a_zone_that_does_not_change_its_clocks_is_unaffected(self):
        assert net_minutes_for(
            day(work_date=date(2026, 10, 24), started=time(20, 0), ended=time(6, 0), breaks=0,
                tz="Asia/Tokyo", crosses_midnight=True)
        ) == 10 * 60


class TestWhatIsRefused:
    def test_an_ordinary_day_is_accepted(self):
        assert problem_with(day()) is None

    def test_an_end_before_the_start_is_refused(self):
        assert problem_with(day(started=time(17, 0), ended=time(9, 0))) is not None

    def test_breaks_longer_than_the_day_are_refused(self):
        assert problem_with(day(started=time(9, 0), ended=time(10, 0), breaks=120)) is not None

    def test_a_time_the_clocks_jumped_over_is_refused(self):
        """29 March 2026, half past two in Vienna: a reading that never existed.

        Silently shifting it would record a time the person did not write.
        """
        problem = problem_with(day(work_date=date(2026, 3, 29), started=time(2, 30), ended=time(10, 0)))
        assert problem is not None
        assert "forward" in problem

    def test_a_day_still_running_is_accepted(self):
        assert problem_with(day(ended=None)) is None
