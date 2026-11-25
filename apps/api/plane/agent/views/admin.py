# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The instance administrators' screen for connected apps (admin app, "Connected apps").

Everything the `agent_client` command does, for somebody who would rather click than log
in to the server. It is the same decision, with the same rules (`services/registry.py`),
so it is open to instance administrators only, through the admin app's own session, and
never to a person's ordinary session or to a connected app's token.

What it shows and does not show:

* the client secret is returned once, when an app is registered or its secret replaced,
  and never again (only its hash is kept);
* the events signing secret is derived, not stored, so it can be shown again, but only to
  an administrator who asks for it, by a POST that leaves a line in the audit log;
* a person's connections are listed (who, since when, which scopes), never their tokens.

Nothing here is cached, because some of it is a secret.
"""

# Django imports
from django.db.models import Count, Q

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.agent import audit
from plane.agent.models import AgentClient, AgentGrant
from plane.agent.scopes import DEFAULT_SCOPES, SCOPES, describe
from plane.agent.services import events, registry
from plane.agent.services.registry import RegistryError
from plane.license.api.views.base import BaseAPIView

# How many connections one app's page lists. The count is exact whatever the limit.
CONNECTIONS_SHOWN = 200


def _bad_request(message):
    return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


def _not_found():
    return Response({"error": "There is no app with that id."}, status=status.HTTP_404_NOT_FOUND)


def _body(request):
    """The JSON object that was sent, or an empty one."""
    data = request.data
    return data if isinstance(data, dict) else {}


def webhook_data(client):
    # "given_up": it was on, and Plane stopped after too many failures in a row.
    if not client.webhook_url:
        state = "off"
    elif client.webhook_disabled_at:
        state = "given_up"
    else:
        state = "on"
    return {
        "url": client.webhook_url,
        "state": state,
        "failures": client.webhook_failures,
        "disabled_at": client.webhook_disabled_at,
    }


def client_data(client, connections):
    return {
        "client_id": client.client_id,
        "name": client.name,
        "description": client.description,
        "redirect_uris": client.redirect_uris,
        "allowed_scopes": client.allowed_scopes,
        "is_active": client.is_active,
        "connections": connections,
        "webhook": webhook_data(client),
        "secret_rotated_at": client.secret_rotated_at,
        "created_at": client.created_at,
    }


def _one(client):
    return client_data(client, registry.live_grants(client).count())


def grant_data(grant):
    return {
        "id": str(grant.id),
        "user": {
            "id": str(grant.user_id),
            "display_name": grant.user.display_name,
            "email": grant.user.email,
        },
        "scopes": grant.scopes,
        "account": {
            "provider": grant.account_provider,
            "username": grant.account_username,
            "name": grant.account_name,
        },
        "created_at": grant.created_at,
        "last_used_at": grant.last_used_at,
    }


class AgentAppBaseEndpoint(BaseAPIView):
    """Instance administrators only (the base class), and never stored by a browser or a proxy."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def app_or_none(self, client_id):
        return AgentClient.objects.filter(client_id=client_id).first()


class AgentAppListEndpoint(AgentAppBaseEndpoint):
    def get(self, request):
        apps = AgentClient.objects.annotate(live=Count("grants", filter=Q(grants__revoked_at__isnull=True))).order_by(
            "name", "created_at"
        )
        return Response(
            {
                "apps": [client_data(app, app.live) for app in apps],
                # What can be asked for, worded as the person approving it will see it.
                "scopes": describe(list(SCOPES)),
                "default_scopes": DEFAULT_SCOPES,
            }
        )

    def post(self, request):
        data = _body(request)
        try:
            client, secret = registry.create_client(
                name=data.get("name"),
                description=data.get("description"),
                redirect_uris=data.get("redirect_uris"),
                scopes=data.get("allowed_scopes"),
            )
        except RegistryError as error:
            return _bad_request(str(error))
        audit.record(
            "app_registered",
            request=request,
            client=client,
            user=request.user,
            name=client.name,
            scopes=client.allowed_scopes,
        )
        return Response({"app": _one(client), "client_secret": secret}, status=status.HTTP_201_CREATED)


class AgentAppEndpoint(AgentAppBaseEndpoint):
    def get(self, request, client_id):
        client = self.app_or_none(client_id)
        return _not_found() if client is None else Response(_one(client))

    def patch(self, request, client_id):
        client = self.app_or_none(client_id)
        if client is None:
            return _not_found()
        data = _body(request)
        try:
            changed = registry.update_client(
                client,
                name=data.get("name"),
                description=data.get("description"),
                redirect_uris=data.get("redirect_uris"),
                allowed_scopes=data.get("allowed_scopes"),
                is_active=data.get("is_active"),
            )
        except RegistryError as error:
            return _bad_request(str(error))
        if changed:
            # Which fields, never their values: the log says that something was done and by whom.
            audit.record("app_changed", request=request, client=client, user=request.user, fields=changed)
        return Response(_one(client))


class AgentAppSecretEndpoint(AgentAppBaseEndpoint):
    def post(self, request, client_id):
        client = self.app_or_none(client_id)
        if client is None:
            return _not_found()
        secret = registry.rotate_secret(client)
        audit.record("app_secret_replaced", request=request, client=client, user=request.user)
        return Response({"app": _one(client), "client_secret": secret})


class AgentAppWebhookEndpoint(AgentAppBaseEndpoint):
    def put(self, request, client_id):
        client = self.app_or_none(client_id)
        if client is None:
            return _not_found()
        url = _body(request).get("url")
        if not isinstance(url, str) or not url.strip():
            return _bad_request("The address is required.")
        try:
            registry.set_webhook(client, url=url.strip())
        except RegistryError as error:
            return _bad_request(str(error))
        audit.record("app_events_changed", request=request, client=client, user=request.user, on=True)
        return Response(_one(client))

    def delete(self, request, client_id):
        client = self.app_or_none(client_id)
        if client is None:
            return _not_found()
        registry.set_webhook(client, off=True)
        audit.record("app_events_changed", request=request, client=client, user=request.user, on=False)
        return Response(_one(client))


class AgentAppWebhookSecretEndpoint(AgentAppBaseEndpoint):
    """Show the secret a delivery is signed with, or replace it (the old one stops matching at once)."""

    def post(self, request, client_id):
        client = self.app_or_none(client_id)
        if client is None:
            return _not_found()
        replace = _body(request).get("replace") is True
        if replace:
            registry.set_webhook(client, new_secret=True)
        audit.record("app_events_secret", request=request, client=client, user=request.user, replaced=replace)
        return Response({"app": _one(client), "webhook_secret": events.webhook_secret(client)})


class AgentAppWebhookTestEndpoint(AgentAppBaseEndpoint):
    def post(self, request, client_id):
        client = self.app_or_none(client_id)
        if client is None:
            return _not_found()
        if not client.webhook_url:
            return _bad_request("Set an address for events first.")
        heard, what = events.send_test(client)
        audit.record("app_events_tested", request=request, client=client, user=request.user, heard=heard)
        return Response({"heard": heard, "detail": what})


class AgentAppConnectionsEndpoint(AgentAppBaseEndpoint):
    def get(self, request, client_id):
        client = self.app_or_none(client_id)
        if client is None:
            return _not_found()
        grants = registry.live_grants(client).select_related("user").order_by("-created_at")
        return Response(
            {
                "total": grants.count(),
                "results": [grant_data(grant) for grant in grants[:CONNECTIONS_SHOWN]],
            }
        )

    def delete(self, request, client_id, grant_id=None):
        """End every connection the app has, or the one named."""
        client = self.app_or_none(client_id)
        if client is None:
            return _not_found()
        if grant_id is not None and not AgentGrant.objects.filter(client=client, id=grant_id).exists():
            return Response({"error": "There is no such connection."}, status=status.HTTP_404_NOT_FOUND)
        ended = registry.revoke_grants(client, grant_id=grant_id, request=request)
        audit.record(
            "app_connections_ended",
            request=request,
            client=client,
            user=request.user,
            count=ended,
            all=grant_id is None,
        )
        return Response({"ended": ended, "app": _one(client)})
