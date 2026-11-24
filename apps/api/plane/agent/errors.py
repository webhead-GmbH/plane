# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The one error shape every connected-app endpoint answers with.

`{"error": "<code>", "error_description": "<sentence>"}` is the shape OAuth 2.0
uses (RFC 6749 section 5.2), so a client library that already understands OAuth
errors reads these without being taught anything. The code is for programs and is
stable; the sentence is for the person reading a log and may be reworded.
"""

# Third-party imports
from rest_framework import status
from rest_framework.exceptions import APIException


class AgentError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, error, description="", status_code=None, headers=None, extra=None):
        super().__init__(detail=description or error)
        self.error = error
        self.description = description
        if status_code is not None:
            self.status_code = status_code
        self.headers = headers or {}
        self.extra = extra or {}

    def body(self):
        body = {"error": self.error}
        if self.description:
            body["error_description"] = self.description
        body.update(self.extra)
        return body


def invalid_request(description, **extra):
    return AgentError("invalid_request", description, extra=extra)


def invalid_grant(description="The code or token is not valid."):
    return AgentError("invalid_grant", description)


def invalid_client(description="The client could not be authenticated."):
    return AgentError(
        "invalid_client",
        description,
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": 'Basic realm="plane-agent"'},
    )


def invalid_token(description="The access token is missing, expired or has been revoked."):
    return AgentError(
        "invalid_token",
        description,
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": 'Bearer realm="plane-agent", error="invalid_token"'},
    )


def insufficient_scope(scope):
    return AgentError(
        "insufficient_scope",
        f"This connection was not granted the '{scope}' scope.",
        status_code=status.HTTP_403_FORBIDDEN,
        headers={"WWW-Authenticate": f'Bearer realm="plane-agent", error="insufficient_scope", scope="{scope}"'},
        extra={"scope": scope},
    )


def not_a_manager():
    return AgentError(
        "not_a_manager",
        "The people connected to this app can see their team only while they are a manager in Plane, and this "
        "person is not one (any longer).",
        status_code=status.HTTP_403_FORBIDDEN,
    )


def not_found(description="No such item, or it is not visible to you."):
    return AgentError("not_found", description, status_code=status.HTTP_404_NOT_FOUND)


def forbidden(description="You are not allowed to do this."):
    return AgentError("forbidden", description, status_code=status.HTTP_403_FORBIDDEN)
