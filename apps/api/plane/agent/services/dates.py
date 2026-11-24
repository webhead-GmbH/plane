# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Reading dates and spans out of a query string without ever answering with a server error."""

# Python imports
from datetime import date, datetime, timedelta

# Module imports
from plane.agent import conf
from plane.agent.errors import invalid_request

# Dates a person could mean. Outside this, the value is a typo, and it must not
# reach `date()` or a year-long loop.
MIN_DATE = date(1970, 1, 1)
MAX_DATE = date(2200, 12, 31)


def parse_date(raw, name):
    if raw in (None, ""):
        return None
    try:
        value = date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise invalid_request(f"{name} must be a date written YYYY-MM-DD.")
    if not MIN_DATE <= value <= MAX_DATE:
        raise invalid_request(f"{name} is out of range.")
    return value


def parse_datetime(raw, name):
    """An ISO 8601 timestamp with a zone. Without one the moment is ambiguous, so it is refused."""
    if raw in (None, ""):
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise invalid_request(f"{name} must be an ISO 8601 timestamp such as 2026-11-19T08:00:00Z.")
    if value.tzinfo is None:
        raise invalid_request(f"{name} must include a time zone, for example Z or +01:00.")
    return value


def parse_span(query, today, *, default_days=7, max_days=None):
    """`from` and `to` (inclusive) from the query, defaulting to a week starting today."""
    max_days = max_days or conf.MAX_RANGE_DAYS
    first = parse_date(query.get("from"), "from") or today
    last = parse_date(query.get("to"), "to") or (first + timedelta(days=default_days - 1))
    if last < first:
        raise invalid_request("to must not be before from.")
    if (last - first).days + 1 > max_days:
        raise invalid_request(f"A span may cover at most {max_days} days.")
    return first, last


def parse_page(query, *, default=None, maximum=None):
    """`limit` and `offset`, clamped."""
    default = default or conf.DEFAULT_PAGE_SIZE
    maximum = maximum or conf.MAX_PAGE_SIZE
    try:
        limit = int(query.get("limit", default))
        offset = int(query.get("offset", 0))
    except (TypeError, ValueError):
        raise invalid_request("limit and offset must be whole numbers.")
    if limit < 1 or offset < 0:
        raise invalid_request("limit must be at least 1 and offset at least 0.")
    return min(limit, maximum), offset
