# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Keeping hours that a settled month already counted from moving underneath it.

Absences, non-project hours and attendance days each carry a marker naming the
month that locked them, and refuse to change once it is set. That marker answers
one question only — was this row counted into a month that has since closed —
and it is stamped at the moment of closing, so it says nothing about a row
written afterwards. A record created today and dated into a month closed last
week carries no marker, and every check that reads one waves it through.

Worklogs cannot carry the marker at all: the month does not own that table, and
stamping HR state onto a row the work-item side writes constantly is not a column
that would stay true.

So the question is asked the other way round, from the day rather than the row.
Given the day something falls on, has that person's month for it stopped being
rebuilt? If it has, the day is part of a figure somebody has already read, and
adding to it or changing it now would leave the figure and the records
disagreeing with no trace of which is right.
"""

# Python imports
from datetime import date

# Module imports
from plane.hr.models import HrEmploymentProfile, HrPeriod
from plane.hr.utils.calendar import hr_local_date

# A month still being rebuilt from its records. Anything else — handed in,
# approved, closed — holds figures that were read as they stood, so the records
# behind them stop moving at the same moment.
IN_PLAY = (HrPeriod.State.OPEN, HrPeriod.State.REOPENED)


def settled_month_for(user_id, *moments):
    """The settled month one of these instants falls in for this person, or None.

    Every profile the person has is checked, not just the one in the workspace the
    request came through. The ledger counts an hour wherever it was logged — the
    company is one company however many workspaces it keeps — so a month closed in
    one of them was closed over this hour too.

    Several instants because an edit has two sides: the day the hour is on now and
    the day it is being moved to. Moving an hour out of a settled month leaves that
    month's total standing while the new month counts it again, which bills it
    twice; moving one in makes it disappear, since the settled month will not be
    rebuilt to notice. Both are refused.
    """
    profiles = list(HrEmploymentProfile.objects.filter(member_id=user_id).select_related("workspace"))
    if not profiles:
        return None

    for profile in profiles:
        tz = profile.timezone or getattr(profile.workspace, "timezone", "") or None
        starts = set()
        for moment in moments:
            if moment is None:
                continue
            day = hr_local_date(moment, tz)
            if day is not None:
                starts.add(date(day.year, day.month, 1))
        if not starts:
            continue

        settled = (
            HrPeriod.objects.filter(profile_id=profile.id, period_start__in=starts).exclude(state__in=IN_PLAY).first()
        )
        if settled is not None:
            return settled

    return None


def settled_month_for_profile(profile, *days):
    """The settled month one of these days falls in for this person, or None.

    For the records that name their profile outright — an absence, an attendance
    day, an hour with no work item. The worklog question above has to find the
    profile first; here it was given.

    Several days because an edit has two sides, the same as moving an hour: the
    day the record sits on now, and the day it is being moved to. Either one being
    settled is enough to leave two months disagreeing about the same hours.
    """
    starts = {date(day.year, day.month, 1) for day in days if day is not None}
    if not starts:
        return None
    return HrPeriod.objects.filter(profile_id=profile.id, period_start__in=starts).exclude(state__in=IN_PLAY).first()


def settled_month_across(profile, start, end):
    """The settled month a date range touches, or None. Both ends included.

    Every month between the two is asked about, not only the ones the range ends
    on. An absence running from January to March passes through February, and a
    February already closed has already counted the days this range would change.
    """
    if start is None or end is None:
        return settled_month_for_profile(profile, start, end)
    if end < start:
        start, end = end, start

    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(date(year, month, 1))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return HrPeriod.objects.filter(profile_id=profile.id, period_start__in=months).exclude(state__in=IN_PLAY).first()


def occurred_at(worklog):
    """The instant an hour is counted from.

    Mirrors what the ledger buckets on, so the guard and the figures agree about
    which month an hour belongs to. Reading it from somewhere else would let an
    hour be refused in one month and counted in another.
    """
    return worklog.started_at or worklog.logged_at
