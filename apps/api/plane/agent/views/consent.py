# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The screens a signed-in person uses to say yes to an app, and to take it back.

These are the only connected-app endpoints that use the person's browser session,
and they are the reason that session needs care: whoever can make a signed-in
browser press "approve" can link their own chat to somebody else's work. So an
approval has to come from the web app itself (its `Origin` is checked, and it has
to be present), as JSON (a form on another site cannot send that without Plane's
consent), carrying a value that was only ever given to a page that was allowed to
read the request.
"""

# Django imports
from django.utils import timezone

# Third-party imports
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# Module imports
from plane.agent import oauth
from plane.agent.errors import forbidden, invalid_request, not_found
from plane.agent.models import AgentGrant
from plane.agent.scopes import describe
from plane.agent.throttles import ConsentRateThrottle
from plane.agent.views.base import AgentResponseMixin
from plane.authentication.session import BaseSessionAuthentication, is_allowed_origin


class SessionView(AgentResponseMixin, APIView):
    authentication_classes = [BaseSessionAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ConsentRateThrottle]
    www_authenticate = None

    def require_web_app(self, request, *, json_body=False):
        """Refuse anything that did not come from Plane's own pages."""
        origin = request.META.get("HTTP_ORIGIN")
        if not origin or not is_allowed_origin(request):
            raise forbidden("This can only be done from Plane's own pages.")
        if json_body and not (request.content_type or "").startswith("application/json"):
            raise invalid_request("Send the request as JSON.")


def _account(row):
    return {
        "provider": row.account_provider,
        "id": row.account_id,
        "username": row.account_username,
        "name": row.account_name,
    }


class ConsentEndpoint(SessionView):
    """What the person is being asked to approve."""

    def get(self, request, request_token):
        row = oauth.find_request(request_token)
        if row is None:
            raise not_found("This link has expired or has already been used.")
        user = request.user
        return Response(
            {
                "client": {"name": row.client.name, "description": row.client.description},
                "account": _account(row),
                "scopes": describe(row.scopes),
                "user": {"id": str(user.id), "display_name": user.display_name, "email": user.email},
                "expires_at": row.expires_at.isoformat(),
                "nonce": oauth.consent_nonce(row, user),
            },
            status=status.HTTP_200_OK,
        )


class _DecisionEndpoint(SessionView):
    decide = None

    def post(self, request, request_token):
        self.require_web_app(request, json_body=True)
        row = oauth.find_request(request_token)
        if row is None:
            raise not_found("This link has expired or has already been used.")
        nonce = request.data.get("nonce") if hasattr(request.data, "get") else None
        if not isinstance(nonce, str):
            raise invalid_request("nonce is required.")
        redirect_to = self.decide(row, request.user, nonce, request=request)
        return Response({"redirect_to": redirect_to}, status=status.HTTP_200_OK)


class ConsentApproveEndpoint(_DecisionEndpoint):
    decide = staticmethod(oauth.approve)


class ConsentDenyEndpoint(_DecisionEndpoint):
    decide = staticmethod(oauth.deny)


def _connection(grant):
    return {
        "id": str(grant.id),
        "app": {"name": grant.client.name, "description": grant.client.description},
        "account": {
            "provider": grant.account_provider,
            "id": grant.account_id,
            "username": grant.account_username,
            "name": grant.account_name,
        },
        "scopes": describe(grant.scopes),
        "created_at": grant.created_at.isoformat(),
        "last_used_at": grant.last_used_at.isoformat() if grant.last_used_at else None,
        "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
    }


def _live_grants(user):
    now = timezone.now()
    return (
        AgentGrant.objects.filter(user=user, revoked_at__isnull=True, client__is_active=True)
        .exclude(expires_at__lte=now)
        .select_related("client")
        .order_by("-created_at")
    )


class ConnectionListEndpoint(SessionView):
    """The apps this person has linked, for the "Connected apps" screen."""

    def get(self, request):
        return Response([_connection(grant) for grant in _live_grants(request.user)], status=status.HTTP_200_OK)


class ConnectionDetailEndpoint(SessionView):
    """Take an app's access back. It stops working on its very next call."""

    def delete(self, request, pk):
        self.require_web_app(request)
        grant = _live_grants(request.user).filter(pk=pk).first()
        if grant is None:
            raise not_found("No such connection.")
        oauth.revoke_grant(grant, oauth.BY_USER, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
