# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Recording when somebody was at work.

The row holds local wall-clock times plus the zone they were given in, because
what is recorded is the person's statement — "I started at eight". Storing the
instant and re-deriving eight o'clock on read would let a timezone database update
rewrite what somebody said.

The elapsed total is a different thing: a duration, meaningful only between
instants. It is resolved once here, when the row is saved, and never recomputed on
read — which is what makes the two clock-change days a year come out right.
"""

# Module imports
from plane.hr.models import HrAttendanceDay
from plane.hr.utils.calendar import elapsed_minutes, is_nonexistent_local_time


def net_minutes_for(day):
    """Minutes worked, breaks taken off.

    Zero while the day is still open. Somebody who has started and not finished
    has no total yet, and inventing one from the current time would make the
    figure change every time anybody looked at it.
    """
    if day.ended_at_local is None:
        return 0

    elapsed = elapsed_minutes(
        day.work_date,
        day.started_at_local,
        day.ended_at_local,
        day.local_timezone,
        crosses_midnight=day.crosses_midnight,
    )
    return elapsed - (day.break_minutes or 0)


def problem_with(day):
    """Why this day cannot be recorded as written, or None.

    Checked here rather than left to the column constraints, because a database
    error tells the person nothing they can act on. The times are their own
    statement, so the answer has to name which part of it does not hold.
    """
    if is_nonexistent_local_time(day.work_date, day.started_at_local, day.local_timezone):
        return "That time did not happen on that date — the clocks went forward over it."

    if day.ended_at_local is None:
        return None

    end_date = day.work_date
    if not day.crosses_midnight and is_nonexistent_local_time(end_date, day.ended_at_local, day.local_timezone):
        return "That time did not happen on that date — the clocks went forward over it."

    minutes = net_minutes_for(day)
    if minutes < 0:
        # Either the end is before the start, or the breaks are longer than the
        # day. Both are somebody mistyping rather than a day worth recording.
        return "The times and breaks do not leave any time worked. Check them over."
    if minutes > 1440:
        return "That is more than a day. If the work ran past midnight, say so."

    return None


def telework_days_in_year(profile, year, up_to=None):
    """Days worked away from the employer's premises in a calendar year.

    A payroll input rather than a convenience: the figure is reported per calendar
    year, and it cannot be reconstructed afterwards from anything else the system
    holds. Counted from the days themselves each time it is asked for, so a day
    corrected later corrects the count with it — a running total kept alongside
    would drift the first time somebody fixed a mistake.

    Stopping at a day gives the figure as it stood then, which is what a month's
    export needs: March's file saying how many had been taken by the end of March,
    rather than how many were taken by December.
    """
    days = HrAttendanceDay.objects.filter(
        profile_id=profile.id,
        work_date__year=year,
        work_location=HrAttendanceDay.WorkLocation.HOME,
    )
    if up_to is not None:
        days = days.filter(work_date__lte=up_to)
    return days.count()


def telework_days_between(profile, first, last):
    """Days worked away from the premises within a window."""
    return HrAttendanceDay.objects.filter(
        profile_id=profile.id,
        work_date__gte=first,
        work_date__lte=last,
        work_location=HrAttendanceDay.WorkLocation.HOME,
    ).count()


def locations_by_day(profile, first, last):
    """Where each day was worked, for the days there is a record of."""
    return {
        day.work_date: day.get_work_location_display()
        for day in HrAttendanceDay.objects.filter(profile_id=profile.id, work_date__gte=first, work_date__lte=last)
    }
