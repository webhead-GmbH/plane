# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The records the module needs before its screens can do anything.

Created by the setup step, and on first use from the screen that needs each one:
the setup step has no button anywhere, so an installation that never ran it had
no holiday calendar — the Public holidays page had nothing to add a day to, and
pressing Add did nothing at all — and no reasons for being away, so nobody could
ask for leave.
"""

# Django imports
from django.utils import timezone

# Module imports
from plane.hr.models import HrAbsenceType, HrHoliday, HrHolidayCalendar

# (code, German name, English name, counts as worked, draws on leave, draws on the
# running balance, needs a document, precedence)
STANDARD_ABSENCE_TYPES = (
    ("urlaub", "Urlaub", "Annual leave", True, True, False, False, 100),
    # Sickness outranks leave, so a day taken ill during booked leave is charged
    # to sickness and the leave stays.
    ("krankenstand", "Krankenstand", "Sick leave", True, False, False, True, 10),
    ("zeitausgleich", "Zeitausgleich", "Time off in lieu", True, False, True, False, 50),
    ("pflegefreistellung", "Pflegefreistellung", "Care leave", True, False, False, False, 20),
    ("dienstverhinderung", "Sonstige Dienstverhinderung", "Other justified absence", True, False, False, False, 30),
    ("unbezahlt", "Unbezahlter Urlaub", "Unpaid leave", False, False, False, False, 200),
)

# Years either side of now that a new calendar is filled in for. Generous because
# past months are entered by hand from the old records, and a year that runs out
# brings back the fault the seeding exists to prevent.
SEEDED_YEARS = 5


def ensure_absence_types(workspace):
    """The usual reasons for being away, if there are none yet. Returns how many were made.

    Only into an empty list: a list somebody has started is theirs, and adding the
    standard set beside it would put two codes on the same reason.
    """
    if HrAbsenceType.objects.exists():
        return 0
    HrAbsenceType.objects.bulk_create(
        [
            HrAbsenceType(
                workspace=workspace,
                code=code,
                name_de=name_de,
                name_en=name_en,
                credits_actual=credits,
                consumes_leave_entitlement=leave,
                consumes_balance=balance,
                requires_document=document,
                precedence=precedence,
            )
            for code, name_de, name_en, credits, leave, balance, document, precedence in STANDARD_ABSENCE_TYPES
        ]
    )
    return len(STANDARD_ABSENCE_TYPES)


def seed_holidays(workspace, calendar, span=SEEDED_YEARS):
    """Fill in the public holidays around now, leaving any already there alone.

    Idempotent, and safe to re-run to extend the range: a day somebody has edited
    is not overwritten. A statutory day somebody removed by hand does come back,
    because nothing records that it was removed.
    """
    from plane.hr.utils.holidays import austrian_holidays

    if calendar.country_code != "AT":
        return 0

    this_year = timezone.now().year
    years = range(this_year - span, this_year + span + 1)
    known = set(HrHoliday.objects.filter(calendar=calendar).values_list("date", flat=True))

    fresh = [
        HrHoliday(
            workspace=workspace,
            calendar=calendar,
            date=day,
            name_de=name_de,
            name_en=name_en,
            day_fraction=fraction,
            is_statutory=is_statutory,
        )
        for year in years
        for day, name_de, name_en, fraction, is_statutory in austrian_holidays(year)
        if day not in known
    ]
    HrHoliday.objects.bulk_create(fresh)
    return len(fresh)


def ensure_default_holiday_calendar(workspace):
    """The calendar everybody without one of their own is measured against.

    Returns the calendar, whether it was made now, and how many days went into it.
    A calendar made here is filled in straight away: an empty one is not a neutral
    start, because every public holiday in it reads as an ordinary working day.
    One that already exists is left exactly as it is.
    """
    calendar = HrHolidayCalendar.objects.filter(is_default=True).first()
    if calendar is not None:
        return calendar, False, 0
    # A national calendar nobody marked as the default is the one that was meant,
    # and a second one beside it would break the one-per-country rule.
    calendar = HrHolidayCalendar.objects.filter(country_code="AT", region_code="").first()
    if calendar is not None:
        calendar.is_default = True
        calendar.save(update_fields=["is_default", "updated_at"])
        return calendar, False, 0
    calendar = HrHolidayCalendar.objects.create(
        workspace=workspace, name="Österreich", country_code="AT", is_default=True
    )
    return calendar, True, seed_holidays(workspace, calendar)
