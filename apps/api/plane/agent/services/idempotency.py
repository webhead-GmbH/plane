# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Doing a write once, however many times the app asks.

The app sends an `Idempotency-Key` header naming the *action it intends*. The first
request with a key does the work and keeps the answer. A repeat with the same key and
the same request gets that answer back and does nothing; a repeat with the same key and
a *different* request is refused, because answering it with the first one's result would
be telling the app something that did not happen.

Only a successful answer is kept. A request that was refused can be fixed and sent again
with the same key.
"""

# Python imports
import hashlib
import json
import re

# Django imports
from django.db import IntegrityError, transaction
from django.utils import timezone

# Module imports
from plane.agent import conf
from plane.agent.errors import AgentError, invalid_request
from plane.agent.models import AgentIdempotencyKey
from plane.agent.tokens import hash_secret

# Printable ASCII with no spaces: what a UUID or a message id looks like. Long enough that
# it cannot be guessed, short enough to be stored and compared cheaply.
KEY_PATTERN = re.compile(r"^[\x21-\x7e]{8,128}$")


def read_key(request):
    """The key the app sent, or a refusal that says what to send."""
    key = request.headers.get("Idempotency-Key", "")
    if not KEY_PATTERN.match(key):
        raise invalid_request(
            "Send an Idempotency-Key header: 8 to 128 printable characters (a UUID is ideal) that names this "
            "one action. Repeating a request with the same key does not do it twice."
        )
    return key


def fingerprint(*parts):
    """A stable hash of what a request asked for."""
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_once(grant, key, request_hash, action):
    """Run `action` unless this key already has an answer. Returns `(status_code, body, replayed)`.

    `action()` returns `(status_code, body)`; only 2xx answers are kept.
    """
    key_hash = hash_secret(key)
    now = timezone.now()
    try:
        with transaction.atomic():
            record = AgentIdempotencyKey.objects.create(
                grant=grant, key_hash=key_hash, request_hash=request_hash, expires_at=now + conf.IDEMPOTENCY_TTL
            )
    except IntegrityError:
        record = AgentIdempotencyKey.objects.filter(grant=grant, key_hash=key_hash).first()
        if record is None:  # deleted between our attempt and our look: start over
            return run_once(grant, key, request_hash, action)
        if record.expires_at <= now:
            record.delete()
            return run_once(grant, key, request_hash, action)
        if record.request_hash != request_hash:
            raise AgentError(
                "idempotency_key_reused",
                "This Idempotency-Key was already used for a different request. Use a new key for a new action.",
                status_code=422,
            )
        if record.status_code is None:
            raise AgentError(
                "request_in_progress",
                "A request with this Idempotency-Key is still being processed. Wait, then repeat it.",
                status_code=409,
                headers={"Retry-After": "2"},
            )
        return record.status_code, record.response_body, True

    try:
        status_code, body = action()
    except BaseException:
        record.delete()
        raise
    if 200 <= status_code < 300:
        record.status_code, record.response_body = status_code, body
        record.save(update_fields=["status_code", "response_body"])
    else:
        record.delete()
    return status_code, body, False
