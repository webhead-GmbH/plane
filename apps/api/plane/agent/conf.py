# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Lifetimes and limits for connected apps, in one place.

Each can be set in the environment, but the defaults are meant to be left alone:
they are short where a leaked value does the most harm (the link a person is sent,
the code it is exchanged for, the access token) and long only where the person
would otherwise have to link again every few days (the refresh token).
"""

# Python imports
import os
from datetime import timedelta


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# How long the link given to a person stays good. Long enough to find a phone and
# sign in; short enough that a link left in a chat history is dead by morning.
REQUEST_LIFETIME = timedelta(seconds=_int("AGENT_REQUEST_LIFETIME_SECONDS", 600))
# What an approval is exchanged for, once. The app is waiting on the redirect, so
# a minute is generous.
CODE_LIFETIME = timedelta(seconds=_int("AGENT_CODE_LIFETIME_SECONDS", 60))
ACCESS_TOKEN_LIFETIME = timedelta(seconds=_int("AGENT_ACCESS_TOKEN_LIFETIME_SECONDS", 3600))
# A refresh token is replaced every time it is used, so this is how long an app may
# go without calling at all before the person has to link again.
REFRESH_TOKEN_LIFETIME = timedelta(days=_int("AGENT_REFRESH_TOKEN_LIFETIME_DAYS", 90))
# However busy the app is, the link ends after this and the person agrees again.
# Zero means no limit.
GRANT_MAX_AGE = timedelta(days=_int("AGENT_GRANT_MAX_AGE_DAYS", 365))
# Two calls with the same refresh token this close together are one app retrying or
# running twice, not a stolen token; further apart, the token has been copied.
REFRESH_REUSE_LEEWAY = timedelta(seconds=_int("AGENT_REFRESH_REUSE_LEEWAY_SECONDS", 10))

# How often a grant's "last used" is written. Every call would be a database write
# on the busiest path for a value people read in minutes.
LAST_USED_RESOLUTION = timedelta(minutes=5)

# How long the record of what apps did is kept.
AUDIT_RETENTION = timedelta(days=_int("AGENT_AUDIT_RETENTION_DAYS", 180))
# How long finished sign-in records and spent tokens are kept after they end.
EXPIRED_RETENTION = timedelta(days=7)

# How long a repeated write with the same Idempotency-Key is answered with the first answer.
IDEMPOTENCY_TTL = timedelta(hours=_int("AGENT_IDEMPOTENCY_RETENTION_HOURS", 24))
# Hours may be added for today and this many days back, no further: an app writing time that
# a payroll month may already have counted should have to say so to a person, not to an API.
MAX_BACKDATE_DAYS = _int("AGENT_MAX_BACKDATE_DAYS", 31)

# Events (see `services/events.py`). A delivery that is not accepted is tried again after these waits, in
# seconds; the app has about half an hour to come back before it is given up on. No wait is longer than ten
# minutes on purpose: a retry waits as an unacknowledged message on the worker, and RabbitMQ closes the
# channel (and with it every task on that worker) of a consumer that holds one for longer than its
# `consumer_timeout`, 30 minutes by default.
WEBHOOK_RETRY_SCHEDULE = (30, 120, 600, 600, 600)
# One attempt may take this long. A bot that cannot answer in ten seconds is not going to be helped by thirty.
WEBHOOK_TIMEOUT_SECONDS = _int("AGENT_WEBHOOK_TIMEOUT_SECONDS", 10)
# Events in a row that could not be delivered at all, after which the address is switched off.
WEBHOOK_FAILURE_LIMIT = _int("AGENT_WEBHOOK_FAILURE_LIMIT", 10)
# Events waiting for one connection. An app that is down while a hundred work items are moved needs
# a poll to catch up, not a hundred stale notifications; past this the newest are dropped.
MAX_PENDING_EVENTS = _int("AGENT_MAX_PENDING_EVENTS", 200)
# How long delivered and failed events are kept, for "why did my bot not hear about this".
EVENT_RETENTION = timedelta(days=_int("AGENT_EVENT_RETENTION_DAYS", 7))

# DRF rate strings.
GRANT_RATE_LIMIT = os.environ.get("AGENT_GRANT_RATE_LIMIT", "120/minute")
# Writes are limited much harder than reads: every one can notify somebody or change what is billed.
WRITE_RATE_LIMIT = os.environ.get("AGENT_WRITE_RATE_LIMIT", "30/minute")
CLIENT_RATE_LIMIT = os.environ.get("AGENT_CLIENT_RATE_LIMIT", "1200/minute")
OAUTH_RATE_LIMIT = os.environ.get("AGENT_OAUTH_RATE_LIMIT", "60/minute")

# Longest span a single call may ask about.
MAX_RANGE_DAYS = 92
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

# The team views work out every person's days one by one, so they ask for less: a shorter span and
# fewer people per call. An app with a larger team pages through it.
TEAM_MAX_RANGE_DAYS = 31
TEAM_DEFAULT_PAGE_SIZE = 20
TEAM_MAX_PAGE_SIZE = 25
