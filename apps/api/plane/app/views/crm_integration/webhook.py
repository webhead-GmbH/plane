# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import hashlib
import hmac
import json
import time

# Third party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

# Module imports
from plane.db.models import CrmIntegration
from plane.utils.crm_events_inbound import CrmEventError, apply_crm_event
from plane.utils.crm_timer_inbound import apply_crm_timer_event
from plane.utils.host import base_host

SIGNATURE_HEADER = "X-Plane-Api-Signature"

# An event is accepted for this long after the CRM sent it. Events are applied
# as they happen, so anything older is a replay, not a late delivery.
MAX_EVENT_AGE_SECONDS = 300


class CrmTimerWebhookThrottle(AnonRateThrottle):
    """Every event comes from the one CRM server, so the anonymous default is too tight."""

    rate = "120/minute"


def _verified_event(request, slug):
    """The integration and the decoded body of a signed CRM event, or an error response.

    There is no Plane session on these requests: the CRM signs the raw body with
    the secret Plane gave it when it registered the webhook, and the signature is
    the only authentication.
    """
    integration = (
        CrmIntegration.objects.filter(workspace__slug=slug, is_active=True).select_related("workspace").first()
    )
    secret = integration.get_timer_webhook_secret() if integration is not None else ""
    if not secret:
        return None, None, Response({"error": "No CRM webhook is registered."}, status=status.HTTP_404_NOT_FOUND)

    body = request.body
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(request.headers.get(SIGNATURE_HEADER, ""), expected):
        return None, None, Response({"error": "Invalid signature."}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = json.loads(body or b"{}")
        sent_at = int(payload.get("sent_at") or 0)
    except (ValueError, TypeError, AttributeError):
        return None, None, Response({"error": "The body is not valid JSON."}, status=status.HTTP_400_BAD_REQUEST)
    if abs(time.time() - sent_at) > MAX_EVENT_AGE_SECONDS:
        return None, None, Response({"error": "The event is too old."}, status=status.HTTP_400_BAD_REQUEST)

    return integration, payload, None


class CrmTimerWebhookEndpoint(APIView):
    """Receive the timers the CRM's own users start and stop.

    Events that need no action are still answered with 200, so the CRM does not
    treat them as failed deliveries.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [CrmTimerWebhookThrottle]

    def post(self, request, slug):
        integration, payload, error = _verified_event(request, slug)
        if error is not None:
            return error

        timer = payload.get("timer")
        if not isinstance(timer, dict):
            return Response({"error": "The event carries no timer."}, status=status.HTTP_400_BAD_REQUEST)

        result = apply_crm_timer_event(integration, payload.get("event"), timer)
        return Response({"result": result}, status=status.HTTP_200_OK)


class CrmEventsWebhookEndpoint(APIView):
    """Receive the projects and ticket tasks made in the CRM.

    The CRM shows its admin what happened, so the answer always says it: what was
    created or updated, with a link, or a fixed ``code`` and a sentence when the
    event could not be applied.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [CrmTimerWebhookThrottle]

    def post(self, request, slug):
        integration, payload, error = _verified_event(request, slug)
        if error is not None:
            return error

        try:
            result = apply_crm_event(
                integration,
                payload.get("event"),
                payload,
                origin=base_host(request=request, is_app=True),
            )
        except CrmEventError as exc:
            return Response({"error": exc.message, "code": exc.code}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(result, status=status.HTTP_200_OK)
