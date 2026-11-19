# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""What a manager's app may be told about the people they manage.

Everything here concerns people who approved nothing themselves, so it is deliberately
thin. For a colleague an app is told which days they work, how many hours they have
worked and how much open work they have: enough to answer "will they be done by next
week" and "who has room for another task". It is never told *why* somebody is away
(that may be sickness, and health information about a named colleague must not be
handed to an app, let alone to a language model behind it), and never any free text.

Two rules decide what is returned, and both are decided on every request:

* the person asking is a manager *now* (the HR module's own rule, `resolve_hr_context`:
  the flag on their employment record, or an instance administrator), so taking the
  flag away ends the app's view on its next call;
* a colleague's work is counted and named only in projects the manager can see
  themselves. The manager flag grants sight of HR figures, not of projects.
"""

# Python imports
from collections import defaultdict
from datetime import timedelta

# Django imports
from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

# Module imports
from plane.agent.errors import not_a_manager, not_found
from plane.agent.services import timekeeping as timing
from plane.agent.services import work_items
from plane.db.models import IssueAssignee, IssueWorkLog
from plane.hr.models import HrEmploymentProfile, HrTimeEntry
from plane.hr.permissions import resolve_hr_context
from plane.hr.services.computation import minutes_from_seconds
from plane.hr.services.ledger import day_outlook, profile_timezone
from plane.hr.utils.calendar import hr_day_bounds_utc, hr_local_date, hr_timezone

# The state groups that still have work left in them.
OPEN_GROUPS = ("backlog", "unstarted", "started")
BUSY_PRIORITIES = ("urgent", "high")
# What a day says about a colleague. Nothing about why they are away.
DAY_FIELDS = ("date", "weekday", "kind", "expects_work", "scheduled_minutes", "expected_minutes")


def require_manager(request):
    """Refuse unless the person behind this connection is a manager at this moment."""
    _profile, is_manager = resolve_hr_context(request)
    if not is_manager:
        raise not_a_manager()


def active_people():
    """The employment records of people who work here now, in a stable order."""
    return (
        HrEmploymentProfile.objects.filter(is_active=True, member__is_active=True, member__is_bot=False)
        .select_related("member", "workspace")
        .order_by("member__display_name", "member_id")
    )


def person_for(user_id):
    """One colleague by their Plane user id, or a 404 that does not say whether they exist."""
    profile = active_people().filter(member_id=work_items.parse_uuid(user_id, "user_id")).first()
    if profile is None:
        raise not_found("No such person on your team.")
    return profile


def zone_of(profile):
    return str(hr_timezone(profile_timezone(profile)))


def person_payload(profile):
    return {"id": str(profile.member_id), "display_name": profile.member.display_name}


def _day(outlook):
    # Always without the kind of absence: see the module docstring.
    payload = timing.day_payload(outlook, with_leave_detail=False)
    return {name: payload[name] for name in DAY_FIELDS}


def capacity(profile, first, last, *, with_days):
    """How many hours this person is expected to work between two days, and which days they are away."""
    outlooks = day_outlook(profile, first, last)
    days = [_day(outlook) for outlook in outlooks]
    result = {
        "expected_minutes": sum(day["expected_minutes"] for day in days),
        "working_days": sum(1 for day in days if day["expects_work"]),
        "days_away": sum(1 for day in days if day["kind"] in ("absence", "partial_absence")),
        # False means nobody has told Plane when this person works, so the figures above are zero for want of
        # a schedule, not because they are away.
        "has_schedule": bool(outlooks) and all(outlook.has_schedule for outlook in outlooks),
    }
    if with_days:
        result["days"] = days
    return result


def worked_minutes(profiles, first, last):
    """Hours each person worked between two of their own local days, as `{user id: {...}}`.

    The same arithmetic as a person's own summary: a day is the *person's* day in *their*
    zone, and seconds are summed per day and per project and rounded once.
    """
    zones = {profile.member_id: zone_of(profile) for profile in profiles}
    lo = hr_day_bounds_utc(first - timedelta(days=1), "UTC")[0]
    hi = hr_day_bounds_utc(last + timedelta(days=1), "UTC")[1]
    rows = (
        IssueWorkLog.objects.filter(logged_by_id__in=list(zones), duration__isnull=False)
        .annotate(occurred=Coalesce("started_at", "logged_at"))
        .filter(occurred__gte=lo, occurred__lt=hi)
        .values("logged_by_id", "occurred", "duration", "project_id")
    )
    seconds = defaultdict(int)
    for row in rows:
        day = hr_local_date(row["occurred"], zones[row["logged_by_id"]])
        if day is not None and first <= day <= last:
            seconds[(row["logged_by_id"], day, row["project_id"])] += row["duration"] or 0
    on_work_items = defaultdict(int)
    for (user_id, _day_, _project), total in seconds.items():
        on_work_items[user_id] += minutes_from_seconds(total)

    other = {
        row["profile_id"]: row["total"] or 0
        for row in HrTimeEntry.objects.filter(
            profile_id__in=[profile.id for profile in profiles], entry_date__gte=first, entry_date__lte=last
        )
        .order_by()
        .values("profile_id")
        .annotate(total=Sum("minutes"))
    }
    result = {}
    for profile in profiles:
        in_items, elsewhere = on_work_items.get(profile.member_id, 0), other.get(profile.id, 0)
        result[profile.member_id] = {
            "total_minutes": in_items + elsewhere,
            "work_item_minutes": in_items,
            "other_minutes": elsewhere,
        }
    return result


def timers_running(profiles):
    """The people, of these, who have a timer running now. Only that fact, never what it runs on."""
    return set(
        IssueWorkLog.objects.filter(logged_by_id__in=[profile.member_id for profile in profiles], duration__isnull=True)
        .values_list("logged_by_id", flat=True)
        .distinct()
    )


def open_work(viewer, profiles, first, last):
    """How much unfinished work each person has, counted over what the manager can see.

    One query for everybody. Somebody who is on a work item through a link that was
    deleted, or who has since left that project, is not counted, as in the web app's lists.
    """
    today = {profile.member_id: hr_local_date(timezone.now(), profile_timezone(profile)) for profile in profiles}
    visible = work_items.visible_issues(viewer).filter(state__group__in=OPEN_GROUPS).values("id")
    rows = (
        IssueAssignee.objects.filter(
            assignee_id__in=list(today),
            issue_id__in=visible,
            assignee__member_project__is_active=True,
            assignee__member_project__project_id=F("project_id"),
        )
        .order_by()
        .values("assignee_id", "issue__target_date", "issue__state__group", "issue__priority")
        .annotate(total=Count("issue_id", distinct=True))
    )
    result = {
        user_id: {
            "count": 0,
            "in_progress": 0,
            "overdue": 0,
            "due_in_span": 0,
            "due_later": 0,
            "no_due_date": 0,
            "urgent_or_high": 0,
        }
        for user_id in today
    }
    for row in rows:
        counts, total, target = result[row["assignee_id"]], row["total"], row["issue__target_date"]
        counts["count"] += total
        if row["issue__state__group"] == "started":
            counts["in_progress"] += total
        if row["issue__priority"] in BUSY_PRIORITIES:
            counts["urgent_or_high"] += total
        if target is None:
            counts["no_due_date"] += total
            continue
        if target < today[row["assignee_id"]]:
            counts["overdue"] += total
        if first <= target <= last:
            counts["due_in_span"] += total
        elif target > last:
            counts["due_later"] += total
    return result
