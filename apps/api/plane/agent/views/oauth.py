# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The endpoints an app calls with its own secret to link a person and keep the link alive."""

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.agent import conf, oauth
from plane.agent.errors import AgentError, invalid_request
from plane.agent.views.base import OAuthView


def _body(request):
    """The request body as a mapping, whatever the caller sent."""
    data = request.data
    if not hasattr(data, "get"):
        raise invalid_request("The request body must be a form or a JSON object.")
    return data


class AuthorizationRequestEndpoint(OAuthView):
    """Register what the app wants to be linked for, and get the link to give the person."""

    def post(self, request):
        data = _body(request)
        client = oauth.authenticate_client(request, data)
        _, token = oauth.create_authorization_request(client, data, request=request)
        return Response(
            {
                "authorization_url": oauth.connect_url(token),
                "expires_in": int(conf.REQUEST_LIFETIME.total_seconds()),
            },
            status=status.HTTP_201_CREATED,
        )


class TokenEndpoint(OAuthView):
    """Spend an approval's code, or a refresh token, for a new pair of tokens."""

    def post(self, request):
        data = _body(request)
        client = oauth.authenticate_client(request, data)
        grant_type = data.get("grant_type")
        if grant_type == "authorization_code":
            result = oauth.exchange_code(client, data, request=request)
        elif grant_type == "refresh_token":
            result = oauth.refresh(client, data, request=request)
        else:
            raise AgentError("unsupported_grant_type", "grant_type must be authorization_code or refresh_token.")
        return Response(result, status=status.HTTP_200_OK)


class RevokeEndpoint(OAuthView):
    """The app has no further use for a token (RFC 7009). Always answers 200."""

    def post(self, request):
        data = _body(request)
        client = oauth.authenticate_client(request, data)
        oauth.revoke_token(client, data, request=request)
        return Response({}, status=status.HTTP_200_OK)
