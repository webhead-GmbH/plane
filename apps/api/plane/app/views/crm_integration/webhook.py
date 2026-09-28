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
from plane.utils.crm_timer_inbound import apply_crm_timer_event

SIGNATURE_HEADER = "X-Plane-Api-Signature"

# An event is accepted for this long after the CRM sent it. Timer events are
# applied as they happen, so anything older is a replay, not a late delivery.
MAX_EVENT_AGE_SECONDS = 300


class CrmTimerWebhookThrottle(AnonRateThrottle):
    """Every event comes from the one CRM server, so the anonymous default is too tight."""

    rate = "120/minute"


class CrmTimerWebhookEndpoint(APIView):
    """Receive the timers the CRM's own users start and stop.

    There is no Plane session on this request: the CRM signs the raw body with
    the secret Plane gave it when it registered the webhook, and the signature is
    the only authentication. Events that need no action are still answered with
    200, so the CRM does not treat them as failed deliveries.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [CrmTimerWebhookThrottle]

    def post(self, request, slug):
        integration = (
            CrmIntegration.objects.filter(workspace__slug=slug, is_active=True).select_related("workspace").first()
        )
        secret = integration.get_timer_webhook_secret() if integration is not None else ""
        if not secret:
            return Response({"error": "No CRM timer webhook is registered."}, status=status.HTTP_404_NOT_FOUND)

        body = request.body
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get(SIGNATURE_HEADER, ""), expected):
            return Response({"error": "Invalid signature."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = json.loads(body or b"{}")
            sent_at = int(payload.get("sent_at") or 0)
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "The body is not valid JSON."}, status=status.HTTP_400_BAD_REQUEST)
        if abs(time.time() - sent_at) > MAX_EVENT_AGE_SECONDS:
            return Response({"error": "The event is too old."}, status=status.HTTP_400_BAD_REQUEST)

        timer = payload.get("timer")
        if not isinstance(timer, dict):
            return Response({"error": "The event carries no timer."}, status=status.HTTP_400_BAD_REQUEST)

        result = apply_crm_timer_event(integration, payload.get("event"), timer)
        return Response({"result": result}, status=status.HTTP_200_OK)
