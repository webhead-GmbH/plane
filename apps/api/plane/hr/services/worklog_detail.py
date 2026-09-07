# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Where a month's hours actually went, entry by entry.

The month has only ever shown a number per day. That number answers "how much"
and nothing else, so the first question anybody asks after reading it — which
work items, and how long on each — has had no screen to ask it on. This builds
the rows behind the number.

Two rules from the ledger are reproduced here rather than re-derived, because a
detail that disagrees with the total it sits under is worse than no detail:

Which day an hour falls on is decided in the *subject's* timezone, from
``COALESCE(started_at, logged_at)``. Never from a ``__date`` lookup — the request
layer activates the *reader's* zone, so the same hour would land on different
days for a manager and for the person whose month it is.

Minutes are rounded once per person, per day, per project, on the summed
seconds. Rounding each entry on its own loses up to half a minute apiece, and a
month of short entries drifts visibly away from the figure it is explaining. So
every row carries raw seconds, and only a subtotal is ever rounded.

A settled month is read from what it counted, not from what is there now. Once a
month stops being rebuilt its stored entry ids are the record; re-running the
live query would show today's entries against yesterday's total.
"""

# Python imports
from collections import defaultdict
from datetime import timedelta

# Django imports
from django.db.models.functions import Coalesce

# Module imports
from plane.db.models import IssueWorkLog
from plane.hr.models import HrPeriod, HrPeriodDay, HrTimeEntry
from plane.hr.services.computation import minutes_from_seconds
from plane.hr.utils.calendar import hr_local_date, hr_month_bounds_utc, month_range

# The states in which a month is still built from its records. Anything else was
# read as it stood, so its detail comes from what it stored.
IN_PLAY = (HrPeriod.State.OPEN, HrPeriod.State.REOPENED)

# What the runaway-timer sweeper puts in front of a note when it closes a timer
# somebody left running. The duration beside it is the cap, not a measurement —
# the sweeper refuses to guess the elapsed time — so the figure is a ceiling
# awaiting correction and a screen that presents it as measured is lying.
AUTO_STOPPED = "[automatically stopped]"

# How the rows may be grouped. Each is a function from a row to a key and a
# label; the screen offers exactly these and nothing else reaches the query.
GROUPINGS = ("day", "work_item", "project", "workspace", "week")

# The groupings whose subtotals add up to the month exactly. The rounding bucket
# is (day, project), so a grouping only fails to close if it can split one. A
# week is a whole number of days, and a project belongs to exactly one
# workspace, so neither can. Only work item can, because one project's day holds
# entries against several of them — and saying otherwise put a caveat about
# arithmetic not closing above arithmetic that closes to the minute.
RECONCILING = ("day", "project", "week", "workspace")


def _profile_zone(profile):
    """The zone this person's days are measured in. Never the reader's."""
    return profile.timezone or getattr(profile.workspace, "timezone", "") or None


def _bucketed_minutes(rows):
    """Minutes for a set of rows, by the ledger's own rule.

    Seconds are summed per (day, project) and rounded once per bucket, which is
    what makes a subtotal here equal the same subtotal in the month.
    """
    seconds = defaultdict(int)
    for row in rows:
        if row["seconds"] is None:
            continue
        seconds[(row["day"], row["project_id"])] += row["seconds"]
    return sum(minutes_from_seconds(total) for total in seconds.values())


def _worklog_rows(profile, first, last, counted=None):
    """One row per hour logged against a work item, in the month's own terms.

    ``counted`` pins the read to a settled month: a mapping of entry id to the
    day that month filed it under. Both halves matter. The ids are looked up
    through ``all_objects`` on purpose, because deleting a work item soft-deletes
    its hours and a closed month that counted them must still be able to say so.
    And the day comes from the mapping rather than from the timestamp, because
    the zone that decided it then is not necessarily the zone this person carries
    now — a profile's timezone is editable, most fall through to the workspace's,
    and neither is guarded against a closed month. Re-deriving the day would move
    rows between days, re-form the rounding buckets, and drop anything that had
    crossed the month boundary in the old zone — reporting a row that is sitting
    there untouched as one that has gone missing.
    """
    tz = _profile_zone(profile)
    pinned = counted is not None
    manager = IssueWorkLog.all_objects if pinned else IssueWorkLog.objects

    query = manager.filter(logged_by_id=profile.member_id)
    if pinned:
        query = query.filter(id__in=list(counted))
    else:
        # Not narrowed to one workspace, and not to projects the reader belongs
        # to. The ledger counts an hour wherever it was logged, so a detail that
        # filtered either would come to less than the total it explains.
        lo, hi = hr_month_bounds_utc(first.year, first.month, tz)
        query = query.annotate(occurred=Coalesce("started_at", "logged_at")).filter(occurred__gte=lo, occurred__lt=hi)

    # No order_by here. The model's default is `-logged_at`, which sorts a
    # backdated entry by the day it was typed, and `-started_at` clumps every
    # hand-written entry together because it has none. The rows are ordered
    # below on the same instant the ledger counts them by.
    query = query.select_related("issue", "project", "workspace")

    rows = []
    for entry in query:
        moment = entry.started_at or entry.logged_at
        day = counted.get(str(entry.id)) if pinned else hr_local_date(moment, tz)
        if day is None:
            continue
        # Only the live read decides membership by the day. A pinned row is in
        # the month by construction — its id came off that month's own day row.
        if not pinned and (day < first or day > last):
            continue
        issue = entry.issue
        project = entry.project
        note = entry.description or ""
        rows.append(
            {
                "id": str(entry.id),
                "day": day,
                # Raw, so a subtotal can be rounded once rather than per row.
                "seconds": entry.duration,
                # A timer still running has no length yet. It is shown rather
                # than hidden — an hour somebody can watch ticking should not be
                # missing from the list explaining their day — and counts nothing.
                "is_running": entry.duration is None,
                # No start time means it was written down afterwards rather than
                # timed, which is the difference somebody querying a figure asks
                # about first.
                "entered_by_hand": entry.started_at is None,
                "started_at": entry.started_at,
                "logged_at": entry.logged_at,
                "note": note,
                # Closed by the sweeper at the cap rather than measured. Said
                # outright, because the alternative is a reader working it out
                # from a marker buried in the note.
                "auto_stopped": note.startswith(AUTO_STOPPED),
                "issue_id": str(issue.id) if issue else None,
                "issue_name": issue.name if issue else "",
                "issue_sequence_id": issue.sequence_id if issue else None,
                "project_id": str(project.id) if project else None,
                "project_name": project.name if project else "",
                "project_identifier": project.identifier if project else "",
                "workspace_id": str(entry.workspace_id) if entry.workspace_id else None,
                "workspace_name": entry.workspace.name if entry.workspace_id else "",
                "gone": entry.deleted_at is not None,
                # Sorted on afterwards, not sent: the screen groups by day and
                # has no business rendering an instant, whose clock time would
                # come out in the reader's zone rather than the subject's.
                "_at": moment,
            }
        )

    rows.sort(key=lambda row: row["_at"], reverse=True)
    for row in rows:
        del row["_at"]
    return rows


def _entry_rows(profile, first, last, ids=None):
    """Hours with no work item behind them — the other half of the day.

    Kept as their own lane rather than mixed in. They have no work item at all,
    their project is optional, and a correction can be negative; presenting them
    as work-item time would put an empty name against a figure and would tell
    the CRM story wrong, since these are the hours that deliberately never reach
    it.
    """
    query = HrTimeEntry.objects.filter(profile_id=profile.id).select_related("project")
    if ids is not None:
        query = query.filter(id__in=list(ids))
    else:
        query = query.filter(entry_date__gte=first, entry_date__lte=last)

    return [
        {
            "id": str(entry.id),
            "day": entry.entry_date,
            "minutes": entry.minutes,
            "category": entry.category,
            "source": entry.source,
            "note": entry.note or "",
            "project_id": str(entry.project_id) if entry.project_id else None,
            "project_name": entry.project.name if entry.project_id else "",
        }
        for entry in query.order_by("-entry_date")
    ]


def _key_and_label(row, grouping):
    """What a row groups under, and what that group is called."""
    if grouping == "work_item":
        if row["issue_id"] is None:
            return "none", ""
        prefix = f"{row['project_identifier']}-{row['issue_sequence_id']}" if row["project_identifier"] else ""
        return row["issue_id"], f"{prefix} {row['issue_name']}".strip()
    if grouping == "project":
        return row["project_id"] or "none", row["project_name"]
    if grouping == "workspace":
        return row["workspace_id"] or "none", row["workspace_name"]
    if grouping == "week":
        # The Monday it began on, and sent as the label too. The earliest day
        # that happens to hold hours is not the week's start, and a header
        # reading "week of" a Thursday tells the reader the wrong seven days.
        monday = row["day"] - timedelta(days=row["day"].weekday())
        return monday.isoformat(), monday.isoformat()
    return row["day"].isoformat(), ""


def group(rows, grouping):
    """The rows gathered under one dimension, largest first."""
    if grouping not in GROUPINGS:
        grouping = "day"

    gathered = {}
    for row in rows:
        key, label = _key_and_label(row, grouping)
        bucket = gathered.setdefault(key, {"key": str(key), "label": label, "rows": []})
        bucket["rows"].append(row)

    groups = []
    for bucket in gathered.values():
        groups.append(
            {
                "key": bucket["key"],
                "label": bucket["label"],
                "minutes": _bucketed_minutes(bucket["rows"]),
                "entries": len(bucket["rows"]),
                # The day the group is named by. For a week that is the Monday
                # it began on, worked or not; for anything else the earliest day
                # it holds, which is what a list sorted by time is sorted on.
                "first_day": (
                    bucket["label"] if grouping == "week" else min(row["day"] for row in bucket["rows"]).isoformat()
                ),
                "rows": bucket["rows"],
            }
        )

    if grouping in ("day", "week"):
        groups.sort(key=lambda item: item["first_day"], reverse=True)
    else:
        groups.sort(key=lambda item: (-item["minutes"], item["label"]))
    return groups


def detail_for(profile, year, month, grouping="day"):
    """A month's hours, entry by entry, grouped as asked.

    Reads only. A closed month is explained by what it counted, an open one by
    what is there now — and nothing here rebuilds anything, because a screen
    that recomputed on being looked at would rewrite figures somebody had
    already read.
    """
    # The local first and last of the month. Taken from the calendar rather than
    # from the UTC bounds: east of Greenwich the lower bound is the previous
    # day's evening, so reading a date off it would start the month a day early.
    first, last = month_range(year, month)

    period = HrPeriod.objects.filter(profile_id=profile.id, period_start=first).first()
    settled = period is not None and period.state not in IN_PLAY

    counted = None
    entry_ids = None
    if settled:
        # The day each entry was filed under, kept alongside its id. That day is
        # what the frozen figures were built from; deriving it again today would
        # answer with whatever zone the person carries now.
        stored = HrPeriodDay.objects.filter(period_id=period.id).values_list(
            "work_date", "worklog_ids", "time_entry_ids"
        )
        counted = {str(identifier): day for day, logged, _ in stored for identifier in (logged or [])}
        entry_ids = [identifier for _, _, entered in stored for identifier in (entered or [])]

    rows = _worklog_rows(profile, first, last, counted=counted)
    entries = _entry_rows(profile, first, last, ids=entry_ids)

    # Counted from what the month recorded against what could be resolved, not
    # from a flag on the rows that came back. A soft-deleted row still returns
    # and can say it is gone; a hard-deleted one returns nothing at all, and
    # only the ids were ever snapshotted — no duration, no name. So the honest
    # figure is the difference, and the screen can say how many rows it cannot
    # show rather than quietly showing fewer.
    missing = max(len(counted) - len(rows), 0) if counted is not None else 0

    return {
        "year": year,
        "month": month,
        "grouping": grouping if grouping in GROUPINGS else "day",
        # Whether these rows are the month's own record or today's answer to the
        # same question. A closed month says so, because its rows can no longer
        # change and its figures no longer move with them.
        "is_settled": settled,
        "period_state": period.state if period else None,
        "work_item_minutes": _bucketed_minutes(rows),
        "other_minutes": sum(entry["minutes"] for entry in entries),
        "running": sum(1 for row in rows if row["is_running"]),
        # Rows the month counted that are no longer there. Naming the count is
        # the difference between a total that looks wrong and one that explains
        # itself.
        "missing": missing,
        "withdrawn": sum(1 for row in rows if row["gone"]),
        # Whether the subtotals below add up to the figure above. They do when
        # the grouping never splits a (day, project) rounding bucket; by work
        # item or by workspace it can, and the screen says so rather than
        # showing arithmetic that quietly does not close.
        "totals_reconcile": (grouping if grouping in GROUPINGS else "day") in RECONCILING,
        "groups": group(rows, grouping),
        "other": entries,
    }
