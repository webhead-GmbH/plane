# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Working out how much time an absence actually covers.

Resolved once, when the absence is recorded, and then left alone. Recomputing it
later against whatever schedule happens to be in force would quietly change how
much leave somebody spent two years ago — and the figure they were granted is the
one they agreed to, not whatever their current contract would imply.
"""

# Module imports
from plane.hr.models import HrWorkSchedule
from plane.hr.services.computation import HALF_DAY, HOURS, _half_day_minutes
from plane.hr.utils.calendar import iter_days
from plane.hr.utils.resolve import credited_day_minutes, effective_schedule


def resolve_total_minutes(absence):
    """How many minutes this absence covers, against the schedule in force now.

    Days the person does not work contribute nothing, so a week of leave over a
    part-time schedule costs only the days they would have worked.
    """
    profile = absence.profile
    personal = list(HrWorkSchedule.objects.filter(profile_id=profile.id))
    defaults = list(HrWorkSchedule.objects.filter(profile__isnull=True))

    total = 0
    for day in iter_days(absence.start_date, absence.end_date):
        schedule = effective_schedule(personal, defaults, day)
        day_minutes = credited_day_minutes(schedule, day)
        if not day_minutes:
            continue

        if absence.granularity == HOURS:
            total += min(absence.minutes_per_day or 0, day_minutes)
        elif absence.granularity == HALF_DAY:
            # Only the ends of a range can be halves; the days between are whole.
            if day == absence.start_date and absence.start_half:
                total += _half_day_minutes(day_minutes, absence.start_half)
            elif day == absence.end_date and absence.end_half:
                total += _half_day_minutes(day_minutes, absence.end_half)
            else:
                total += day_minutes
        else:
            total += day_minutes
    return total
