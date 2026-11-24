# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Housekeeping for connected apps: nothing here changes what anybody may do."""

# Django imports
from django.utils import timezone

# Third-party imports
from celery import shared_task

# Module imports
from plane.agent import conf
from plane.agent.models import AgentAuditLog, AgentAuthorizationRequest, AgentEvent, AgentIdempotencyKey, AgentToken
from plane.utils.exception_logger import log_exception


def purge_expired(now=None):
    """Delete sign-in requests and tokens that ended a while ago, and old audit lines.

    A token that has expired is already refused, so removing it changes nothing a
    caller can see; it only keeps the tables from growing by a row per app per
    hour for ever. Grants are kept (they are the history of who had access), and so
    is anything the audit retention has not yet reached.
    """
    now = now or timezone.now()
    cutoff = now - conf.EXPIRED_RETENTION
    return {
        "requests": AgentAuthorizationRequest.objects.filter(expires_at__lt=cutoff).delete()[0],
        "tokens": AgentToken.objects.filter(expires_at__lt=cutoff).delete()[0],
        "audit_lines": AgentAuditLog.objects.filter(created_at__lt=now - conf.AUDIT_RETENTION).delete()[0],
        "idempotency_keys": AgentIdempotencyKey.objects.filter(expires_at__lt=now).delete()[0],
        # Whatever the state: one still waiting after the retention window was never going to be sent.
        "events": AgentEvent.objects.filter(created_at__lt=now - conf.EVENT_RETENTION).delete()[0],
    }


@shared_task
def purge_expired_agent_records():
    try:
        return purge_expired()
    except Exception as error:  # noqa: BLE001 - a failed sweep is retried tomorrow
        log_exception(error)
        return None


@shared_task
def dispatch_activity_events(activity_ids):
    """Work out who the activities just recorded are news to, and make an event for each."""
    from plane.agent.services import events

    try:
        return events.dispatch_activities(activity_ids)
    except Exception as error:  # noqa: BLE001 - telling an app is never a reason for anything else to fail
        log_exception(error)
        return None


@shared_task(bind=True)
def deliver_agent_event(self, event_id):
    """Tell the app about one event; if it does not answer, try again later.

    The waits and the number of tries come from `conf.WEBHOOK_RETRY_SCHEDULE`, and the number
    of attempts is counted on the event itself, so a worker that dies mid-way does not reset it.
    """
    from plane.agent.services import events

    try:
        event = AgentEvent.objects.select_related("grant", "grant__client").filter(pk=event_id).first()
        if event is None:
            return None
        outcome, wait = events.deliver_once(event)
    except Exception as error:  # noqa: BLE001
        log_exception(error)
        return None
    if outcome == events.RETRY:
        raise self.retry(countdown=wait, max_retries=None)
    return outcome
