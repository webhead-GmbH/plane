# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Point the CRM's timer events, and its project and ticket-task events, at Plane.

Plane registers the webhook itself, over the connection it already has to the
CRM, whenever the integration is saved or tested: the admin configures nothing
new on the CRM side, and a changed address or secret is picked up on the next
save. The CRM keeps one webhook per API key, and with it the workspace the key
belongs to, which is what the CRM lists in its project form.
"""

# Python imports
import logging

# Django imports
from django.conf import settings

# Module imports
from plane.utils.crm_client import CrmApiClient, CrmApiError

logger = logging.getLogger("plane.worker")

TIMER_WEBHOOK_PATH = "/api/workspaces/{slug}/crm-integration/timer-webhook/"
EVENTS_WEBHOOK_PATH = "/api/workspaces/{slug}/crm-integration/events/"

# The registration runs inside the admin's request, like the connection test.
REGISTRATION_TIMEOUT = 15


def _webhook_url(path, workspace_slug, request=None):
    base = settings.CRM_WEBHOOK_BASE_URL or (request.build_absolute_uri("/") if request is not None else "")
    if not base:
        return None
    return base.rstrip("/") + path.format(slug=workspace_slug)


def timer_webhook_url(workspace_slug, request=None):
    """The URL the CRM posts timer events to, or None when no base address is known."""
    return _webhook_url(TIMER_WEBHOOK_PATH, workspace_slug, request)


def events_webhook_url(workspace_slug, request=None):
    """The URL the CRM posts its projects and ticket tasks to, or None when no base address is known."""
    return _webhook_url(EVENTS_WEBHOOK_PATH, workspace_slug, request)


def register_timer_webhook(integration, request=None):
    """Register this workspace's timer webhook with the CRM.

    Returns ``(True, None)`` or ``(False, reason)``, where the reason is one of a
    few fixed codes — never the CRM's own error text, which goes to the log. A
    failure is reported but never raised: saving the integration must not fail
    because the CRM could not be told where to send its timers, and the next save
    retries.
    """
    if not integration.is_active:
        return False, "integration_inactive"
    api_key = integration.get_api_key()
    if not integration.crm_api_url or not api_key:
        return False, "credentials_missing"

    url = timer_webhook_url(integration.workspace.slug, request)
    if url is None:
        return False, "plane_address_unknown"

    client = CrmApiClient(
        base_url=integration.crm_api_url,
        api_key=api_key,
        timeout=REGISTRATION_TIMEOUT,
        verify=settings.CRM_VERIFY_SSL,
    )
    workspace = integration.workspace
    try:
        client.register_timer_webhook(
            url=url,
            secret=integration.ensure_timer_webhook_secret(),
            workspace_slug=workspace.slug,
            workspace_name=workspace.name,
            events_url=events_webhook_url(workspace.slug, request),
        )
    except CrmApiError as exc:
        logger.warning("Could not register the CRM timer webhook for %s: %s", integration.workspace.slug, exc)
        return False, "crm_request_failed"
    return True, None


def unregister_timer_webhook(integration):
    """Tell the CRM to forget this workspace, before the integration is deleted.

    Best effort: the integration is deleted either way. A CRM that cannot be told
    keeps offering the workspace in its project form, and its events are refused
    (no integration answers them) until someone removes the API key there.
    """
    api_key = integration.get_api_key()
    if not integration.crm_api_url or not api_key:
        return
    client = CrmApiClient(
        base_url=integration.crm_api_url,
        api_key=api_key,
        timeout=REGISTRATION_TIMEOUT,
        verify=settings.CRM_VERIFY_SSL,
    )
    try:
        client.unregister_timer_webhook()
    except CrmApiError as exc:
        logger.warning("Could not unregister the CRM webhook for %s: %s", integration.workspace.slug, exc)
