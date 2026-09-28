# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Point the CRM's timer events at Plane.

Plane registers the webhook itself, over the connection it already has to the
CRM, whenever the integration is saved or tested: the admin configures nothing
new on the CRM side, and a changed address or secret is picked up on the next
save. The CRM keeps one webhook per API key.
"""

# Python imports
import logging

# Django imports
from django.conf import settings

# Module imports
from plane.utils.crm_client import CrmApiClient, CrmApiError

logger = logging.getLogger("plane.worker")

TIMER_WEBHOOK_PATH = "/api/workspaces/{slug}/crm-integration/timer-webhook/"

# The registration runs inside the admin's request, like the connection test.
REGISTRATION_TIMEOUT = 15


def timer_webhook_url(workspace_slug, request=None):
    """The URL the CRM posts timer events to, or None when no base address is known."""
    base = settings.CRM_WEBHOOK_BASE_URL or (request.build_absolute_uri("/") if request is not None else "")
    if not base:
        return None
    return base.rstrip("/") + TIMER_WEBHOOK_PATH.format(slug=workspace_slug)


def register_timer_webhook(integration, request=None):
    """Register this workspace's timer webhook with the CRM.

    Returns ``(True, None)`` or ``(False, reason)``. A failure is logged and
    reported but never raised: saving the integration must not fail because the
    CRM could not be told where to send its timers, and the next save retries.
    """
    if not integration.is_active:
        return False, "The integration is inactive."
    api_key = integration.get_api_key()
    if not integration.crm_api_url or not api_key:
        return False, "The CRM URL and API key are required."

    url = timer_webhook_url(integration.workspace.slug, request)
    if url is None:
        return False, "Plane's own address is unknown; set CRM_WEBHOOK_BASE_URL."

    client = CrmApiClient(
        base_url=integration.crm_api_url,
        api_key=api_key,
        timeout=REGISTRATION_TIMEOUT,
        verify=settings.CRM_VERIFY_SSL,
    )
    try:
        client.register_timer_webhook(url=url, secret=integration.ensure_timer_webhook_secret())
    except CrmApiError as exc:
        logger.warning("Could not register the CRM timer webhook for %s: %s", integration.workspace.slug, exc)
        return False, str(exc)
    return True, None
