# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Deciding which day, and therefore which month, a moment belongs to.

Every date question in this module goes through here, and the reason is narrow and
important. Timestamps are stored in UTC, but the request layer activates the
*requesting* user's own timezone before a view runs, so a Django ``__date`` lookup
on a timestamp answers differently depending on who is looking. A manager and the
person they are looking at would see the same hour fall in different months.
Background jobs, which have no requesting user, would give a third answer.

So: no ``__date`` lookups on timestamps anywhere in this module. Ranges are built
here, in one declared zone, and compared as half-open intervals — closed at the
start, open at the end. An inclusive range would count anything landing exactly on
the boundary instant in both of the months either side of it.
"""

# Python imports
import zoneinfo
from datetime import date, datetime, time, timedelta

# Django imports
from django.conf import settings

# Module imports
from plane.hr.conf import DEFAULT_HR_TIMEZONE

UTC = zoneinfo.ZoneInfo("UTC")


def hr_timezone(name=None):
    """Resolve a zone, falling back to the configured default and then to UTC.

    An unknown zone name must not take the whole month's figures down with it, so
    a bad value degrades to the default rather than raising.
    """
    for candidate in (name, getattr(settings, "HR_TIMEZONE", None), DEFAULT_HR_TIMEZONE):
        if not candidate:
            continue
        try:
            return zoneinfo.ZoneInfo(candidate)
        except zoneinfo.ZoneInfoNotFoundError:
            continue
    return UTC


def hr_local_date(moment, tz=None):
    """The calendar date a moment falls on, in the given zone.

    Converting an instant to a local date is unambiguous in this direction even
    across a clock change: the hour that occurs twice in autumn produces two
    different instants, but both land on the same date, which is all that is
    needed here.
    """
    if moment is None:
        return None
    return moment.astimezone(hr_timezone(tz)).date()


def hr_day_bounds_utc(day, tz=None):
    """Half-open UTC bounds covering one local day: ``[start, end)``."""
    zone = hr_timezone(tz)
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def hr_month_bounds_utc(year, month, tz=None):
    """Half-open UTC bounds covering one local month: ``[start, end)``.

    Safe across clock changes without any special handling, because they always
    fall on the last Sunday of March and October and so never on the first of a
    month. Midnight on the first is never an ambiguous or non-existent time.
    """
    zone = hr_timezone(tz)
    first = date(year, month, 1)
    next_first = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    start = datetime.combine(first, time.min, tzinfo=zone)
    end = datetime.combine(next_first, time.min, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def month_range(year, month):
    """First and last local dates of a month, inclusive — for iterating days."""
    first = date(year, month, 1)
    next_first = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, next_first - timedelta(days=1)


def iter_days(first, last):
    """Every date from ``first`` to ``last`` inclusive."""
    current = first
    while current <= last:
        yield current
        current += timedelta(days=1)


def elapsed_minutes(work_date, started, ended, tz, crosses_midnight=False):
    """Minutes between two local wall-clock times, resolved through real instants.

    Subtracting the clock times directly would be wrong twice a year: on the day
    the clocks go back, eight in the evening to six in the morning is ten elapsed
    hours rather than nine, and on the day they go forward it is eight.

    The start is read as the earlier of an ambiguous pair and the end as the later,
    so a shift spanning the repeated hour is credited with the time actually spent
    rather than an hour less.
    """
    zone = hr_timezone(tz)
    end_date = work_date + timedelta(days=1) if crosses_midnight else work_date
    start_at = datetime.combine(work_date, started, tzinfo=zone).replace(fold=0)
    end_at = datetime.combine(end_date, ended, tzinfo=zone).replace(fold=1)
    delta = end_at.astimezone(UTC) - start_at.astimezone(UTC)
    return int(delta.total_seconds() // 60)


def is_nonexistent_local_time(day, at, tz):
    """Whether a wall-clock time never happened, because the clocks jumped over it.

    Somebody entering half past two on the morning the clocks go forward has
    written down a time that did not exist, and they should be told rather than
    have it silently shifted.
    """
    zone = hr_timezone(tz)
    naive = datetime.combine(day, at)
    localised = naive.replace(tzinfo=zone)
    # A time that exists survives a round trip through UTC unchanged; one that was
    # skipped comes back as a different wall-clock reading.
    round_tripped = localised.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    return round_tripped != naive
