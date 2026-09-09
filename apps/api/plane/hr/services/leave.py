# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""How much leave somebody has left.

The entitlement says what was agreed for a leave year; the absences say what has
been taken out of it. Until the two are put together neither answers the only
question anybody actually asks before booking a week off, and the figure people
would fall back on is the spreadsheet this module exists to replace.

Worked out from the absences themselves rather than read off the month ledger.
An absence is a record whether or not anybody has opened the month it falls in,
whereas the ledger's stored days appear only once a month has been built — and a
leave year runs from a hire anniversary, so it reaches back across months nobody
has had reason to open. Reading the stored days would quietly overstate what is
left, which is the direction that lets somebody book leave they do not have.

The arithmetic, though, is the ledger's own, run over the window rather than over
a month. A public holiday inside a booked week costs no leave, and sickness
recorded over booked leave takes the day instead of it — so counting the range
day by day here, in ignorance of both, would tell somebody they had spent leave
the month they can also see says they still have.
"""

# Module imports
from plane.hr.models import HrLeaveEntitlement
from plane.hr.services.ledger import leave_charged_between


def entitlement_covering(profile, day):
    """The leave year that day falls in, or None where none is on record.

    None rather than an empty year: nobody has said what this person's leave is,
    and a zero would read as the different and much more alarming statement that
    they have none.
    """
    return (
        HrLeaveEntitlement.objects.filter(
            profile_id=profile.id,
            leave_year_start__lte=day,
            leave_year_end__gte=day,
        )
        .order_by("-leave_year_start")
        .first()
    )


def taken_between(profile, first, last):
    """Leave counted against the entitlement between two days, inclusive.

    Only what has actually been agreed to — the ledger counts approved absences
    and nothing else, and a request still waiting on somebody is not yet leave
    taken. Counting it here would show a balance that a refusal silently puts
    back, and would disagree with the month besides.
    """
    return leave_charged_between(profile, first, last)


def standing(profile, day):
    """What this person's leave account comes to on a given day, or None.

    Held and returned in minutes. Turning it into days is a display decision that
    depends on the schedule in force at the moment of display, so it is made where
    the schedule is known and never stored.
    """
    entitlement = entitlement_covering(profile, day)
    if entitlement is None:
        return None

    granted = entitlement.granted_minutes
    taken = taken_between(profile, entitlement.leave_year_start, entitlement.leave_year_end)

    return {
        "leave_year_start": entitlement.leave_year_start,
        "leave_year_end": entitlement.leave_year_end,
        "granted_minutes": granted,
        "taken_minutes": taken,
        # Signed: somebody can be over, having been allowed leave in advance, and
        # showing that as zero would hide the thing worth knowing.
        "remaining_minutes": granted - taken,
        "is_final": entitlement.is_final,
    }
