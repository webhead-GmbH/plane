# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Finding the record that was in force on a given day.

Contracts, schedules and rates are all dated slices, and the answer to "what
applied here" is always resolved per day rather than per month. That is what makes
a change agreed halfway through a month cost nothing: the days before it find the
old row and the days after find the new one, with no special case anywhere.

Every lookup here takes a pre-fetched list rather than querying, because the caller
is normally walking a whole month and would otherwise issue one query per day.
"""

# Python imports
from bisect import bisect_right


def _covers(record, day):
    if record.valid_from > day:
        return False
    return record.valid_to is None or record.valid_to >= day


def effective(records, day):
    """The record covering ``day``, or None.

    Where several cover the same day — which the constraints permit only for a
    personal record sitting on top of a workspace default — the latest start wins.
    """
    best = None
    for record in records:
        if _covers(record, day) and (best is None or record.valid_from > best.valid_from):
            best = record
    return best


def effective_schedule(personal, defaults, day):
    """The schedule for a day: the person's own if they have one, else the default."""
    return effective(personal, day) or effective(defaults, day)


def scheduled_minutes(schedule, day):
    """Expected minutes on a day. Zero when there is no schedule at all."""
    if schedule is None:
        return 0
    return schedule.minutes_for(day)


def credited_day_minutes(schedule, day):
    """Minutes credited for a day the person does not work but is paid for.

    Under a flexitime agreement this is the notional day the agreement names rather
    than whatever the schedule happens to say, because the point of such an
    agreement is that the daily distribution is the person's to choose — so there
    is no meaningful "what they would have worked" to read off the schedule.
    """
    if schedule is None:
        return 0
    if schedule.is_flexible and schedule.notional_daily_minutes is not None:
        # Still nothing on a day that is not a working day at all.
        return schedule.notional_daily_minutes if schedule.minutes_for(day) else 0
    return schedule.minutes_for(day)


class HolidayLookup:
    """Holidays for one calendar, indexed for repeated lookup across a month."""

    def __init__(self, holidays):
        self._by_date = {holiday.date: holiday for holiday in holidays}

    def get(self, day):
        return self._by_date.get(day)

    def __contains__(self, day):
        return day in self._by_date


class AbsenceLookup:
    """Absences for one person, searchable by day.

    Ranges are kept sorted by start so a day lookup can skip everything starting
    after it, rather than scanning the whole set once per day of the month.
    """

    def __init__(self, absences):
        self._absences = sorted(absences, key=lambda absence: absence.start_date)
        self._starts = [absence.start_date for absence in self._absences]

    def covering(self, day):
        """Every absence whose range includes this day."""
        cutoff = bisect_right(self._starts, day)
        return [absence for absence in self._absences[:cutoff] if absence.end_date >= day]
