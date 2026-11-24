# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""What a person's days look like and how they have spent them, for a connected app.

The working-day facts come from the HR ledger's own arithmetic (see
`day_outlook`), so an app is never told something the month will later contradict.
Hours are summed the way the ledger sums them: per day and per project on the raw
seconds, rounded once, because rounding every entry on its own loses most of a
minute apiece.
"""

# Python imports
from collections import defaultdict

# Django imports
from django.db.models.functions import Coalesce
from django.utils import timezone

# Module imports
from plane.agent.services import work_items
from plane.db.models import IssueWorkLog
from plane.hr.models import HrAbsence, HrTimeEntry
from plane.hr.services import computation
from plane.hr.services.computation import minutes_from_seconds
from plane.hr.utils.calendar import hr_day_bounds_utc, hr_local_date

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

KIND_NAMES = {
    computation.KIND_WORKDAY: "workday",
    computation.KIND_NON_WORKING: "non_working_day",
    computation.KIND_HOLIDAY: "public_holiday",
    computation.KIND_HALF_HOLIDAY: "half_public_holiday",
    computation.KIND_ABSENCE: "absence",
    computation.KIND_PARTIAL_ABSENCE: "partial_absence",
}
GRANULARITY_NAMES = {
    computation.FULL_DAY: "full_day",
    computation.HALF_DAY: "half_day",
    computation.HOURS: "hours",
}
HALF_NAMES = {computation.MORNING: "morning", computation.AFTERNOON: "afternoon"}


def absence_type_name(absence_type):
    return absence_type.name_en or absence_type.name_de


def day_payload(outlook, *, with_leave_detail):
    """One day as an app is told about it.

    That a day is an absence is working-day information, and an app needs it to know
    not to ask for a report. *What kind* of absence is the person's business, and is
    given only when they allowed it: it may be sickness, and the reason for a sick day
    is health information. The free-text reason on the absence is never given.
    """
    holiday = None
    if outlook.holiday is not None:
        holiday = {
            "name": outlook.holiday.name_en or outlook.holiday.name_de,
            "fraction": float(outlook.holiday.day_fraction),
        }
    absences = []
    for absence, applies in outlook.absences:
        entry = {
            "granularity": GRANULARITY_NAMES.get(applies.granularity, "full_day"),
            "half": HALF_NAMES.get(applies.half),
            "minutes": applies.minutes,
        }
        if with_leave_detail:
            entry["type"] = {"code": absence.absence_type.code, "name": absence_type_name(absence.absence_type)}
        absences.append(entry)
    return {
        "date": outlook.day.isoformat(),
        "weekday": WEEKDAYS[outlook.day.weekday()],
        "kind": KIND_NAMES.get(outlook.kind, "workday"),
        "expects_work": outlook.expected_minutes > 0,
        "scheduled_minutes": outlook.scheduled_minutes,
        "expected_minutes": outlook.expected_minutes,
        "has_schedule": outlook.has_schedule,
        "holiday": holiday,
        "absences": absences,
    }


def approved_absences(profile, first, last):
    return (
        HrAbsence.objects.filter(
            profile_id=profile.id,
            state=HrAbsence.State.APPROVED,
            start_date__lte=last,
            end_date__gte=first,
        )
        .select_related("absence_type")
        .order_by("start_date")
    )


def _bounds(first, last, zone):
    return hr_day_bounds_utc(first, zone)[0], hr_day_bounds_utc(last, zone)[1]


def worked_rows(user, first, last, zone):
    """Finished hours on work items between two local days, as plain rows."""
    lo, hi = _bounds(first, last, zone)
    rows = (
        IssueWorkLog.objects.filter(logged_by=user, duration__isnull=False)
        .annotate(occurred=Coalesce("started_at", "logged_at"))
        .filter(occurred__gte=lo, occurred__lt=hi)
        .values("occurred", "duration", "project_id", "issue_id")
    )
    result = []
    for row in rows:
        day = hr_local_date(row["occurred"], zone)
        if day is not None and first <= day <= last:
            result.append({**row, "day": day})
    return result


def summarize(user, profile, first, last, zone, *, with_work_items):
    """Hours between two local days: per day, and per work item when allowed."""
    rows = worked_rows(user, first, last, zone)

    by_bucket = defaultdict(int)
    for row in rows:
        by_bucket[(row["day"], row["project_id"])] += row["duration"] or 0
    work_item_by_day = defaultdict(int)
    for (day, _project), seconds in by_bucket.items():
        work_item_by_day[day] += minutes_from_seconds(seconds)

    other_by_day = defaultdict(int)
    if profile is not None:
        for entry in HrTimeEntry.objects.filter(profile_id=profile.id, entry_date__gte=first, entry_date__lte=last):
            other_by_day[entry.entry_date] += entry.minutes

    days = []
    for day in sorted(set(work_item_by_day) | set(other_by_day)):
        in_work_items, other = work_item_by_day.get(day, 0), other_by_day.get(day, 0)
        days.append(
            {
                "date": day.isoformat(),
                "minutes": in_work_items + other,
                "work_item_minutes": in_work_items,
                "other_minutes": other,
            }
        )

    summary = {
        "from": first.isoformat(),
        "to": last.isoformat(),
        "timezone": zone,
        "total_minutes": sum(item["minutes"] for item in days),
        "work_item_minutes": sum(work_item_by_day.values()),
        "other_minutes": sum(other_by_day.values()),
        "days": days,
        "work_items": None,
    }

    if with_work_items:
        seconds_by_issue = defaultdict(int)
        entries_by_issue = defaultdict(int)
        for row in rows:
            seconds_by_issue[row["issue_id"]] += row["duration"] or 0
            entries_by_issue[row["issue_id"]] += 1
        visible = {
            issue.id: issue
            for issue in work_items.with_relations(
                work_items.with_my_time(work_items.visible_issues(user).filter(id__in=list(seconds_by_issue)), user)
            )
        }
        items = []
        for issue_id, seconds in seconds_by_issue.items():
            issue = visible.get(issue_id)
            items.append(
                {
                    "minutes": minutes_from_seconds(seconds),
                    "entries": entries_by_issue[issue_id],
                    # Time on something the person can no longer see is still time they
                    # worked, so it is counted, but nothing is said about what it was.
                    "work_item": work_items.compact(issue) if issue is not None else None,
                }
            )
        items.sort(key=lambda item: -item["minutes"])
        summary["work_items"] = items[:50]
    return summary


def running_timer(user, *, with_work_item):
    """The timer the person has running, wherever it is, or None."""
    log = (
        IssueWorkLog.objects.filter(logged_by=user, duration__isnull=True)
        .select_related("issue", "project", "workspace")
        .order_by("-started_at", "-logged_at")
        .first()
    )
    if log is None:
        return None
    started = log.started_at or log.logged_at
    payload = {
        "started_at": started.isoformat(),
        "elapsed_minutes": max(int((timezone.now() - started).total_seconds() // 60), 0),
        "note": log.description or "",
        "work_item": None,
    }
    if with_work_item:
        issue = work_items.with_relations(
            work_items.with_my_time(work_items.visible_issues(user).filter(id=log.issue_id), user)
        ).first()
        payload["work_item"] = work_items.compact(issue) if issue is not None else None
    return payload
