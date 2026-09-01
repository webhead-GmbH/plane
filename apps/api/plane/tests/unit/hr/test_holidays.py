# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Austria's public holidays.

Four of the thirteen move with Easter, so these are computed rather than listed.
A wrong date here is a day somebody is charged a full shortfall for not working
when they were not entitled to, or credited for one that was an ordinary working
day — and it repeats every year until somebody notices.

The anchors below are real dates, checked against the calendar rather than
against the code, so the test cannot agree with a wrong implementation.
"""

# Python imports
from datetime import date
from decimal import Decimal

# Third-party imports
import pytest

# Module imports
from plane.hr.utils.holidays import austrian_holidays, easter_sunday

pytestmark = [pytest.mark.unit]


class TestEaster:
    @pytest.mark.parametrize(
        "year,expected",
        [
            (2020, date(2020, 4, 12)),
            (2021, date(2021, 4, 4)),
            (2022, date(2022, 4, 17)),
            (2023, date(2023, 4, 9)),
            (2024, date(2024, 3, 31)),
            (2025, date(2025, 4, 20)),
            (2026, date(2026, 4, 5)),
            (2027, date(2027, 3, 28)),
            (2028, date(2028, 4, 16)),
            (2030, date(2030, 4, 21)),
            # Century boundaries, where a wrong computus usually shows up first.
            (2000, date(2000, 4, 23)),
            (2100, date(2100, 3, 28)),
        ],
    )
    def test_it_lands_on_the_right_day(self, year, expected):
        assert easter_sunday(year) == expected

    def test_it_is_always_a_sunday(self):
        assert all(easter_sunday(year).weekday() == 6 for year in range(1583, 2601))

    def test_it_refuses_a_year_the_gregorian_calendar_did_not_cover(self):
        # Answering anyway would be a plausible date for a calendar not yet in use.
        with pytest.raises(ValueError):
            easter_sunday(1500)

    def test_it_always_falls_in_the_only_window_it_can(self):
        # 22 March to 25 April, by definition. Anything outside is arithmetic that
        # happened to produce a valid date.
        for year in range(1583, 2601):
            day = easter_sunday(year)
            assert date(year, 3, 22) <= day <= date(year, 4, 25)


class TestTheCalendar:
    def test_there_are_thirteen_statutory_holidays(self):
        statutory = [row for row in austrian_holidays(2026) if row[4]]
        assert len(statutory) == 13

    def test_good_friday_is_not_among_them(self):
        # It stopped being a holiday for members of certain churches after the 2019
        # ruling, and was never a general public holiday. Including it would credit
        # everybody a day a year they are not entitled to.
        good_friday = easter_sunday(2026).toordinal() - 2
        assert all(day.toordinal() != good_friday for day, *_ in austrian_holidays(2026))

    @pytest.mark.parametrize(
        "name,weekday",
        [
            ("Ostermontag", 0),
            ("Christi Himmelfahrt", 3),
            ("Pfingstmontag", 0),
            ("Fronleichnam", 3),
        ],
    )
    def test_the_moveable_feasts_never_drift_off_their_weekday(self, name, weekday):
        for year in range(1990, 2101):
            # Matched loosely because a day shared with a fixed holiday carries
            # both names, and the weekday still has to hold for it.
            found = next(day for day, de, *_ in austrian_holidays(year) if name in de)
            assert found.weekday() == weekday, f"{name} {year} landed on the wrong day"

    def test_the_fixed_ones_are_where_they_should_be(self):
        days = {de: day for day, de, *_ in austrian_holidays(2026)}
        assert days["Neujahr"] == date(2026, 1, 1)
        assert days["Nationalfeiertag"] == date(2026, 10, 26)
        assert days["Mariä Himmelfahrt"] == date(2026, 8, 15)
        assert days["Christtag"] == date(2026, 12, 25)
        assert days["Stefanitag"] == date(2026, 12, 26)

    def test_christmas_eve_and_new_years_eve_are_half_days_by_agreement(self):
        # Not statutory, so they carry no pay entitlement of their own — which is
        # why they are marked rather than simply listed alongside the rest.
        by_date = {day: row for day, *row in austrian_holidays(2026)}
        for day in (date(2026, 12, 24), date(2026, 12, 31)):
            _, _, fraction, is_statutory = by_date[day]
            assert fraction == Decimal("0.5")
            assert is_statutory is False

    def test_a_statutory_holiday_is_never_a_part_day(self):
        for _, _, _, fraction, is_statutory in austrian_holidays(2026):
            if is_statutory:
                assert fraction == Decimal("1")

    def test_the_fraction_is_exact_rather_than_a_float(self):
        # It is stored in a decimal column and then multiplied by a day's minutes.
        assert all(isinstance(row[3], Decimal) for row in austrian_holidays(2026))

    def test_they_can_be_left_out_where_they_are_not_agreed(self):
        rows = austrian_holidays(2026, include_customary_half_days=False)
        assert len(rows) == 13
        assert all(is_statutory for *_, is_statutory in rows)

    def test_no_two_holidays_ever_land_on_the_same_date(self):
        # The calendar stores one row per date, so a pair sharing one would abort
        # the whole year's seeding rather than show up as a wrong figure. Swept
        # well past the next occurrence, because stopping at a round year is how
        # the ones after it get missed.
        for year in range(1583, 2601):
            days = [day for day, *_ in austrian_holidays(year)]
            assert len(days) == len(set(days)), f"{year} has a collision"

    def test_two_holidays_on_one_day_are_one_day_off(self):
        # Ascension falls on the Staatsfeiertag whenever Easter is 23 March. 2008
        # was the last time; nobody got two days for it.
        assert easter_sunday(2008) == date(2008, 3, 23)
        may_day = next(row for row in austrian_holidays(2008) if row[0] == date(2008, 5, 1))
        _, name_de, name_en, fraction, is_statutory = may_day
        assert name_de == "Staatsfeiertag / Christi Himmelfahrt"
        assert name_en == "State Holiday / Ascension Day"
        assert fraction == Decimal("1")
        assert is_statutory is True
        assert sum(1 for row in austrian_holidays(2008) if row[0].month == 5) == 3

    def test_every_holiday_falls_inside_the_year_asked_for(self):
        for year in (1999, 2026, 2027, 2100):
            assert all(day.year == year for day, *_ in austrian_holidays(year))

    def test_they_come_back_in_date_order(self):
        days = [day for day, *_ in austrian_holidays(2026)]
        assert days == sorted(days)
