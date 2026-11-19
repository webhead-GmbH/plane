# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Telling a connected app that something happened, so that it does not have to ask.

An event is a hint, not a record: it says *that* something happened to a work item of one
connected person, by id, and nothing else. The app then asks for the details with that
person's own token, which decides again, at that moment, what they may see. So an event can
never carry anything its person could not read, and a stolen signing secret reveals only
that somebody was assigned something.

Delivery is at least once. A failed delivery is retried for about half an hour and then
given up on, and an address that keeps failing is switched off, so events can be late,
repeated or (after an outage) missing. An app that needs to be certain reconciles with
`GET /work-items/?updated_since=`; the id of an event is the same on every retry, for
removing the repeats.

Where an app is told is never chosen by the app. An administrator sets the address; it must
be HTTPS (or a host the operator has trusted for plain HTTP), it is checked against the same
internal-address rules as Plane's own webhooks at the moment it is set and again on every
delivery, the connection is pinned to the address that was checked, redirects are never
followed, and the app's answer is never read.
"""

# Python imports
import hashlib
import hmac
import json
import time
from collections import defaultdict
from urllib.parse import urlsplit

# Django imports
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

# Third-party imports
import requests

# Module imports
from plane.agent import audit, conf
from plane.agent.models import AgentClient, AgentEvent, AgentGrant
from plane.agent.scopes import WORK_ITEMS_READ
from plane.agent.services import work_items
from plane.db.models import Issue, IssueActivity, IssueAssignee
from plane.utils.ip_address import validate_url
from plane.utils.url_security import pinned_fetch

ASSIGNED = "work_item.assigned"
UNASSIGNED = "work_item.unassigned"
DUE_DATE_CHANGED = "work_item.due_date_changed"
STATE_CHANGED = "work_item.state_changed"
CONNECTION_REVOKED = "connection.revoked"
EVENT_TYPES = (ASSIGNED, UNASSIGNED, DUE_DATE_CHANGED, STATE_CHANGED, CONNECTION_REVOKED)

# The fields of an activity that become events, and nothing else does.
WATCHED_FIELDS = ("assignees", "target_date", "state")

# What the person is told when a connection they did not end themselves was ended.
REVOKED_REASONS = {"user": "user", "admin": "admin", "code_reuse": "security", "token_reuse": "security"}

# Outcomes of one attempt at delivery.
DELIVERED = "delivered"
RETRY = "retry"
GAVE_UP = "gave_up"

SECRET_PREFIX = "plane_whsec_"
SIGNATURE_HEADER = "X-Plane-Agent-Signature"
TIMESTAMP_HEADER = "X-Plane-Agent-Timestamp"
EVENT_HEADER = "X-Plane-Agent-Event"
DELIVERY_HEADER = "X-Plane-Agent-Delivery"


# --- Where, and signed with what ----------------------------------------------


def webhook_secret(client):
    """What the app verifies deliveries with.

    Derived, not stored, from the server's secret key, this client and a version number: a
    copy of the database holds nothing a delivery could be forged with. Raising the client's
    `webhook_secret_version` is how it is changed; changing the server's secret key changes
    every one.
    """
    message = f"plane-agent-webhook:{client.id}:{client.webhook_secret_version}".encode("utf-8")
    digest = hmac.new(settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return SECRET_PREFIX + digest


def sign(secret, timestamp, body):
    """`v1=` and the HMAC-SHA256 of `<timestamp>.<body>`: what the app recomputes and compares."""
    mac = hmac.new(secret.encode("utf-8"), f"{timestamp}.".encode("ascii") + body, hashlib.sha256).hexdigest()
    return f"v1={mac}"


def check_webhook_url(url):
    """Refuse an address that is not safe to send events to. Returns it normalised, or raises ValueError.

    HTTPS only, unless the operator has said the host is theirs (`WEBHOOK_ALLOWED_HOSTS`, the
    setting Plane's own webhooks use for internal services). Hosts that resolve to internal
    addresses are refused unless `WEBHOOK_ALLOWED_IPS` allows them.
    """
    parts = urlsplit(url or "")
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError("The address must be an https:// address.")
    if parts.username or parts.password or parts.fragment:
        raise ValueError("The address must not carry credentials or a fragment.")
    trusted = parts.hostname.rstrip(".").lower() in settings.WEBHOOK_ALLOWED_HOSTS
    if parts.scheme != "https" and not trusted:
        raise ValueError("The address must be https://, unless the host is listed in WEBHOOK_ALLOWED_HOSTS.")
    validate_url(url, allowed_ips=settings.WEBHOOK_ALLOWED_IPS, allowed_hosts=settings.WEBHOOK_ALLOWED_HOSTS)
    return url


def has_listeners():
    """Whether any app is waiting to be told anything. One cheap query, asked before any work is done."""
    return AgentClient.objects.filter(is_active=True, webhook_disabled_at__isnull=True).exclude(webhook_url="").exists()


# --- Making events ------------------------------------------------------------


def announce_activities(activities):
    """Called with the activities Plane has just recorded for a work item. Cheap, and never raises."""
    ids = [
        str(activity.id) for activity in activities if activity.field in WATCHED_FIELDS and activity.verb == "updated"
    ]
    if not ids or not has_listeners():
        return
    from plane.agent.tasks import dispatch_activity_events

    dispatch_activity_events.delay(ids)


def _current_assignees(issue_id):
    return set(
        IssueAssignee.objects.filter(
            issue_id=issue_id,
            assignee__member_project__is_active=True,
            assignee__member_project__project_id=F("project_id"),
        ).values_list("assignee_id", flat=True)
    )


def _affected(activity, assignees_of):
    """Who an activity is news to, as `(event type, person id)`."""
    if activity.field == "assignees":
        if activity.new_identifier:
            return [(ASSIGNED, activity.new_identifier)]
        if activity.old_identifier:
            return [(UNASSIGNED, activity.old_identifier)]
        return []
    kind = DUE_DATE_CHANGED if activity.field == "target_date" else STATE_CHANGED
    return [(kind, person_id) for person_id in assignees_of(activity.issue_id)]


def _listening_grants(person_ids):
    """The live connections of these people whose app has an address to tell and may see work items."""
    now = timezone.now()
    grants = (
        AgentGrant.objects.filter(
            user_id__in=person_ids,
            user__is_active=True,
            revoked_at__isnull=True,
            client__is_active=True,
            client__webhook_disabled_at__isnull=True,
        )
        .exclude(client__webhook_url="")
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .select_related("client", "user")
    )
    by_person = defaultdict(list)
    for grant in grants:
        if WORK_ITEMS_READ in (grant.scopes or []):
            by_person[grant.user_id].append(grant)
    return by_person


def dispatch_activities(activity_ids):
    """Turn recorded activities into events for the people they concern. Returns how many were made."""
    activities = list(
        IssueActivity.objects.filter(id__in=activity_ids, field__in=WATCHED_FIELDS, verb="updated").order_by(
            "created_at"
        )
    )
    if not activities:
        return 0

    cache = {}

    def assignees_of(issue_id):
        if issue_id not in cache:
            cache[issue_id] = _current_assignees(issue_id)
        return cache[issue_id]

    # One event per person, work item and kind, however many times it changed in one go.
    plans = {}
    for activity in activities:
        for kind, person_id in _affected(activity, assignees_of):
            # What somebody did themselves, for example through their own app, is not news to them.
            if person_id is not None and person_id != activity.actor_id:
                plans.setdefault((kind, activity.issue_id, person_id), activity)
    if not plans:
        return 0

    grants = _listening_grants({person_id for _kind, _issue, person_id in plans})
    if not grants:
        return 0
    issues = {
        issue.id: issue
        for issue in Issue.issue_objects.filter(id__in={issue_id for _kind, issue_id, _person in plans}).select_related(
            "project", "workspace"
        )
    }

    made = 0
    for (kind, issue_id, person_id), activity in plans.items():
        issue = issues.get(issue_id)
        if issue is None:
            continue
        for grant in grants.get(person_id, ()):
            # Decided now, for this person, as every read is: a work item they cannot see is not announced.
            if not work_items.visible_issues(grant.user).filter(id=issue_id).exists():
                continue
            data = {
                "workspace": issue.workspace.slug,
                "work_item": {
                    "id": str(issue.id),
                    "ref": work_items.reference(issue),
                    "project_id": str(issue.project_id),
                },
            }
            made += 1 if create_event(grant, kind, data, created_at=activity.created_at) else 0
    return made


def announce_revoked(grant, reason):
    """Tell the app that a person's connection was ended by somebody other than the app itself."""
    told = REVOKED_REASONS.get(reason)
    if told is None or not grant.client.webhook_url or grant.client.webhook_disabled_at or not grant.client.is_active:
        return None
    return create_event(grant, CONNECTION_REVOKED, {"reason": told})


def create_event(grant, kind, data, *, created_at=None):
    """Record an event and arrange for it to be sent once the transaction it was made in is final."""
    waiting = AgentEvent.objects.filter(grant=grant, status=AgentEvent.Status.PENDING).count()
    if waiting >= conf.MAX_PENDING_EVENTS:
        return None
    event = AgentEvent.objects.create(
        grant=grant, event_type=kind, payload=data, created_at=created_at or timezone.now()
    )

    def send():
        from plane.agent.tasks import deliver_agent_event

        deliver_agent_event.delay(str(event.id))

    transaction.on_commit(send)
    return event


# --- Delivering ---------------------------------------------------------------


def envelope(event):
    """What the app is sent: ids and the kind of thing that happened."""
    grant = event.grant
    return {
        "id": str(event.id),
        "type": event.event_type,
        "created_at": event.created_at.isoformat(),
        "connection": {
            "id": str(grant.id),
            "account": {"provider": grant.account_provider, "id": grant.account_id},
        },
        "data": event.payload,
    }


def body_of(event):
    return json.dumps(envelope(event), separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")


def _finish(event, status, *, error="", status_code=None):
    event.status = status
    event.last_error = error[:200]
    event.last_status_code = status_code
    if status == AgentEvent.Status.DELIVERED:
        event.delivered_at = timezone.now()
    event.save(update_fields=["status", "attempts", "last_error", "last_status_code", "delivered_at"])


def _count_failure(client):
    """One more event the app could not be told about. Past the limit its address is switched off."""
    AgentClient.objects.filter(pk=client.pk).update(webhook_failures=F("webhook_failures") + 1)
    client.refresh_from_db(fields=["webhook_failures", "webhook_disabled_at"])
    if client.webhook_failures >= conf.WEBHOOK_FAILURE_LIMIT and client.webhook_disabled_at is None:
        switch_off(client, "failures")


def switch_off(client, why):
    AgentClient.objects.filter(pk=client.pk, webhook_disabled_at__isnull=True).update(
        webhook_disabled_at=timezone.now()
    )
    audit.record("webhook_disabled", client=client, reason=why)


def deliver_once(event):
    """One attempt at telling the app. Returns `(outcome, seconds to wait before the next try)`.

    The app's answer is only looked at for its status: any 2xx is "heard". Its body is not
    read, so what a hostile or broken app sends back costs nothing and goes nowhere.
    """
    if event.status != AgentEvent.Status.PENDING:
        return GAVE_UP, 0
    grant = event.grant
    client = grant.client
    if not client.is_active or not client.webhook_url or client.webhook_disabled_at is not None:
        event.attempts += 1
        _finish(event, AgentEvent.Status.FAILED, error="not_deliverable")
        return GAVE_UP, 0
    # News about work is for a connection that is still there; that it ended is the one thing sent after.
    if event.event_type != CONNECTION_REVOKED and not (grant.is_usable() and grant.user.is_active):
        event.attempts += 1
        _finish(event, AgentEvent.Status.FAILED, error="connection_ended")
        return GAVE_UP, 0

    body = body_of(event)
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Plane-Agent-Events/1",
        SIGNATURE_HEADER: sign(webhook_secret(client), timestamp, body),
        TIMESTAMP_HEADER: timestamp,
        EVENT_HEADER: event.event_type,
        # The same on every retry of this event: what the app removes repeats by.
        DELIVERY_HEADER: str(event.id),
    }
    event.attempts += 1
    try:
        response = pinned_fetch(
            "POST",
            client.webhook_url,
            allowed_ips=settings.WEBHOOK_ALLOWED_IPS,
            allowed_hosts=settings.WEBHOOK_ALLOWED_HOSTS,
            headers=headers,
            data=body,
            timeout=conf.WEBHOOK_TIMEOUT_SECONDS,
            stream=True,
        )
    except ValueError:
        # The address is no longer one Plane will send to. It will not become one by waiting.
        _finish(event, AgentEvent.Status.FAILED, error="address_refused")
        switch_off(client, "address_refused")
        return GAVE_UP, 0
    except requests.RequestException as error:
        return _failed_attempt(event, client, error=type(error).__name__)

    status_code = response.status_code
    response.close()
    if 200 <= status_code < 300:
        _finish(event, AgentEvent.Status.DELIVERED, status_code=status_code)
        if client.webhook_failures:
            AgentClient.objects.filter(pk=client.pk).update(webhook_failures=0)
        return DELIVERED, 0
    return _failed_attempt(event, client, error="http_status", status_code=status_code)


def _failed_attempt(event, client, *, error, status_code=None):
    schedule = conf.WEBHOOK_RETRY_SCHEDULE
    if event.attempts > len(schedule):
        _finish(event, AgentEvent.Status.FAILED, error=error, status_code=status_code)
        _count_failure(client)
        return GAVE_UP, 0
    event.last_error = error[:200]
    event.last_status_code = status_code
    event.save(update_fields=["attempts", "last_error", "last_status_code"])
    return RETRY, schedule[event.attempts - 1]
