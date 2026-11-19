# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""What a connected app may be given, and how each piece is worded to the person approving it.

A scope is a promise made on the consent screen, so each one is narrow and named for
what it lets the app *see or do*, not for the endpoint behind it. The consent screen
lists every scope it is asked for; nothing is granted that was not shown.

Anything that reveals more than the app needs to do its job is a scope of its own.
Whether somebody is off today is `time:read`, because a bot has to know it to avoid
asking for a daily report; *why* they are off is `leave:read`, because the reason
can be health information.
"""

# Python imports
from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    id: str
    # English wording, used by clients that do not translate. The web app looks the
    # scope up by id in its own translations first.
    title: str
    description: str
    # Whether it lets the app change anything.
    writes: bool = False


PROFILE = "profile"
TIME_READ = "time:read"
LEAVE_READ = "leave:read"
WORK_ITEMS_READ = "work_items:read"
WORK_ITEMS_WRITE = "work_items:write"
TIME_WRITE = "time:write"

_SCOPES = (
    Scope(
        PROFILE,
        "Your name and workspaces",
        "Your name, your time zone and the workspaces you belong to.",
    ),
    Scope(
        TIME_READ,
        "Your working days and time",
        "Whether each day is a working day, a public holiday or a day off for you, the hours you have worked, and the "
        "work item your timer is running on.",
    ),
    Scope(
        LEAVE_READ,
        "Your leave",
        "Your leave balance, and the kind of absence (for example holiday or sick leave) booked on a day off.",
    ),
    Scope(
        WORK_ITEMS_READ,
        "Your projects and work items",
        "The projects you are a member of and the work items you can see in them, with their comments.",
    ),
    Scope(
        WORK_ITEMS_WRITE,
        "Create and change work items for you",
        "Create work items, change their state, priority, dates, assignees and labels, and add comments, as you. "
        "Everything it does shows in Plane under your name.",
        writes=True,
    ),
    Scope(
        TIME_WRITE,
        "Track your time",
        "Start and stop your timer, and add hours to your time, as you.",
        writes=True,
    ),
)

SCOPES = {scope.id: scope for scope in _SCOPES}
# What an app is registered for when nobody names scopes: everything that cannot change anything.
READ_ONLY_SCOPES = [scope.id for scope in _SCOPES if not scope.writes]


def parse_scope_string(value):
    """The scopes in a space-delimited `scope` parameter, in order and without repeats."""
    seen = []
    for item in (value or "").split():
        if item not in seen:
            seen.append(item)
    return seen


def unknown_scopes(scopes):
    return [scope for scope in scopes if scope not in SCOPES]


def describe(scope_ids):
    """The scopes as the consent screen shows them."""
    return [
        {
            "id": SCOPES[scope_id].id,
            "title": SCOPES[scope_id].title,
            "description": SCOPES[scope_id].description,
            "writes": SCOPES[scope_id].writes,
        }
        for scope_id in scope_ids
        if scope_id in SCOPES
    ]
