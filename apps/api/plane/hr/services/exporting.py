# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""What gets handed to the payroll accountant, and to each person.

Two shapes. One row per person for the month, which is what replaces the
spreadsheet; and one row per day for a single person, which is what they get if
they want to know where a figure came from.

Hours go out in both minutes and decimal hours. Payroll works in decimal hours,
but a decimal figure has already been rounded, and when somebody disputes fifteen
minutes the exact figure needs to be there too.
"""

# Python imports
from io import BytesIO, StringIO

# Module imports
from plane.hr.models import HrPeriod, HrPeriodDay
from plane.hr.services.ledger import period_totals
from plane.utils.porters.formatters import CSVFormatter, XLSXFormatter

MONTH_COLUMNS = [
    "employee",
    "email",
    "period_start",
    "period_end",
    "state",
    "target_minutes",
    "target_hours",
    "actual_minutes",
    "actual_hours",
    "balance_minutes",
    "balance_hours",
    "project_minutes",
    "non_project_minutes",
    "absence_minutes",
    "holiday_minutes",
    "leave_consumed_minutes",
    "opening_balance_minutes",
    "closing_balance_minutes",
]

DAY_COLUMNS = [
    "date",
    "day_kind",
    "target_minutes",
    "project_minutes",
    "non_project_minutes",
    "absence_minutes",
    "holiday_minutes",
    "actual_minutes",
    "balance_minutes",
    "needs_review",
    "note",
]


def _hours(minutes):
    """Decimal hours, to two places. Rounded for reading, never for arithmetic."""
    if minutes is None:
        return ""
    return round(minutes / 60, 2)


def _figures(period):
    """The figures for a month, from wherever they currently live."""
    if period.state == HrPeriod.State.LOCKED:
        return {
            "target_minutes": period.target_minutes or 0,
            "actual_minutes": period.actual_minutes or 0,
            "balance_minutes": period.balance_minutes or 0,
            "project_minutes": period.project_minutes or 0,
            "non_project_minutes": period.non_project_minutes or 0,
            "absence_minutes": period.absence_minutes or 0,
            "holiday_minutes": period.holiday_minutes or 0,
            "leave_consumed_minutes": period.leave_consumed_minutes or 0,
        }
    totals = period_totals(period)
    return {key: (totals.get(key) or 0) for key in (
        "target_minutes",
        "actual_minutes",
        "balance_minutes",
        "project_minutes",
        "non_project_minutes",
        "absence_minutes",
        "holiday_minutes",
        "leave_consumed_minutes",
    )}


def month_rows(periods):
    """One row per person, for a month."""
    rows = []
    for period in periods:
        figures = _figures(period)
        member = period.profile.member
        rows.append(
            {
                "employee": member.display_name or "",
                "email": member.email or "",
                "period_start": period.period_start.isoformat(),
                "period_end": period.period_end.isoformat(),
                "state": period.get_state_display(),
                "target_minutes": figures["target_minutes"],
                "target_hours": _hours(figures["target_minutes"]),
                "actual_minutes": figures["actual_minutes"],
                "actual_hours": _hours(figures["actual_minutes"]),
                "balance_minutes": figures["balance_minutes"],
                "balance_hours": _hours(figures["balance_minutes"]),
                "project_minutes": figures["project_minutes"],
                "non_project_minutes": figures["non_project_minutes"],
                "absence_minutes": figures["absence_minutes"],
                "holiday_minutes": figures["holiday_minutes"],
                "leave_consumed_minutes": figures["leave_consumed_minutes"],
                "opening_balance_minutes": period.opening_balance_minutes or "",
                "closing_balance_minutes": period.closing_balance_minutes or "",
            }
        )
    return rows


def day_rows(period):
    """One row per day, for a single person's month."""
    days = HrPeriodDay.objects.filter(period_id=period.id).order_by("work_date")
    return [
        {
            "date": day.work_date.isoformat(),
            "day_kind": day.get_day_kind_display(),
            "target_minutes": day.target_minutes,
            "project_minutes": day.project_minutes,
            "non_project_minutes": day.non_project_minutes,
            "absence_minutes": day.absence_minutes,
            "holiday_minutes": day.holiday_minutes,
            "actual_minutes": day.actual_minutes,
            "balance_minutes": day.balance_minutes,
            "needs_review": "yes" if day.needs_review else "",
            "note": day.note or "",
        }
        for day in days
    ]


def render(rows, columns, file_format):
    """Rows into a file, with the columns in a fixed order.

    Fixed on purpose: whatever reads this at the other end is looking for columns
    in the order it was told to expect, and a spreadsheet whose columns move
    between months is worse than no export at all.
    """
    ordered = [{column: row.get(column, "") for column in columns} for row in rows]
    if file_format == "csv":
        return CSVFormatter().encode(ordered), "text/csv"
    if file_format == "xlsx":
        return (
            XLSXFormatter().encode(ordered),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    raise ValueError("Only CSV and XLSX can be produced.")


def as_stream(payload):
    """A file-like object for whichever of the two the formatter produced."""
    return BytesIO(payload) if isinstance(payload, bytes) else StringIO(payload)
