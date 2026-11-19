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
from plane.agent.models import AgentAuditLog, AgentAuthorizationRequest, AgentIdempotencyKey, AgentToken
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
    }


@shared_task
def purge_expired_agent_records():
    try:
        return purge_expired()
    except Exception as error:  # noqa: BLE001 - a failed sweep is retried tomorrow
        log_exception(error)
        return None
