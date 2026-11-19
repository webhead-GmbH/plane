# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""What every connected-app endpoint has in common."""

# Django imports
from django.http import Http404

# Third-party imports
from rest_framework import exceptions, status
from rest_framework.parsers import FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

# Module imports
from plane.agent import audit
from plane.agent.authentication import AgentPrincipal, AgentTokenAuthentication
from plane.agent.errors import AgentError
from plane.agent.permissions import HasRequiredScope
from plane.agent.throttles import ClientRateThrottle, GrantRateThrottle, OAuthRateThrottle

BEARER = 'Bearer realm="plane-agent"'


class AgentResponseMixin:
    """One error shape, and responses that nothing may keep.

    `Cache-Control: no-store` is on every answer: they carry tokens, or one person's
    hours and work, and neither belongs in a shared cache or a proxy's disk.
    """

    renderer_classes = [JSONRenderer]
    parser_classes = [JSONParser, FormParser]
    # What a request with no credentials is told to send. None where the caller
    # signs in some other way (the web app's own session).
    www_authenticate = BEARER

    def handle_exception(self, exc):
        if isinstance(exc, AgentError):
            return Response(exc.body(), status=exc.status_code, headers=exc.headers)
        if isinstance(exc, exceptions.AuthenticationFailed):
            headers = (
                {"WWW-Authenticate": f'{self.www_authenticate}, error="invalid_token"'} if self.www_authenticate else {}
            )
            return Response(
                {"error": "invalid_token", "error_description": "The access token is not valid."},
                status=status.HTTP_401_UNAUTHORIZED,
                headers=headers,
            )
        if isinstance(exc, exceptions.NotAuthenticated):
            headers = {"WWW-Authenticate": self.www_authenticate} if self.www_authenticate else {}
            return Response(
                {"error": "unauthorized", "error_description": "Authentication is required."},
                status=status.HTTP_401_UNAUTHORIZED,
                headers=headers,
            )
        if isinstance(exc, exceptions.PermissionDenied):
            return Response(
                {"error": "forbidden", "error_description": str(exc.detail)}, status=status.HTTP_403_FORBIDDEN
            )
        if isinstance(exc, exceptions.Throttled):
            headers = {"Retry-After": str(int(exc.wait))} if exc.wait else {}
            return Response(
                {"error": "rate_limited", "error_description": "Too many requests. Slow down and retry later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers=headers,
            )
        if isinstance(exc, (exceptions.NotFound, Http404)):
            return Response(
                {"error": "not_found", "error_description": "No such item, or it is not visible to you."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if isinstance(exc, exceptions.MethodNotAllowed):
            return Response({"error": "method_not_allowed"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        if isinstance(exc, exceptions.UnsupportedMediaType):
            return Response(
                {"error": "invalid_request", "error_description": "Send JSON or a form-encoded body."},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
        if isinstance(exc, exceptions.ParseError):
            return Response(
                {"error": "invalid_request", "error_description": "The request body could not be read."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(exc, exceptions.ValidationError):
            return Response(
                {"error": "invalid_request", "error_description": "Some fields are not valid.", "fields": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Anything else is a fault on our side. It is not described to the caller.
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class OAuthView(AgentResponseMixin, APIView):
    """The endpoints an app calls with its own secret, before any person has a token.

    They sign the *client* in by hand (so a wrong secret and an unknown client look
    the same) and are limited by the address the call comes from.
    """

    authentication_classes = []
    permission_classes = []
    throttle_classes = [OAuthRateThrottle]


class AgentAPIView(AgentResponseMixin, APIView):
    """An endpoint a connected app calls on behalf of the person who linked it.

    Subclasses name the one scope they need as `required_scope`. Reads only: a view
    that should accept anything else lists the methods itself.
    """

    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [IsAuthenticated, HasRequiredScope]
    throttle_classes = [GrantRateThrottle, ClientRateThrottle]
    http_method_names = ["get", "head", "options"]
    required_scope = None
    # For a path that reads with one scope and changes with another: `{"GET": ..., "PATCH": ...}`.
    required_scopes = None

    def scope_for(self, method):
        """The one scope this endpoint needs for this HTTP method, or None if it names none."""
        if self.required_scopes:
            return self.required_scopes.get("GET" if method == "HEAD" else method)
        return self.required_scope

    @classmethod
    def all_scopes(cls):
        """Every scope the endpoint names, for tests and documentation."""
        return set((cls.required_scopes or {}).values()) | ({cls.required_scope} - {None})

    @property
    def grant(self):
        return self.request.auth.grant

    @property
    def audit_detail(self):
        """What a view wants written beside the call: ids only, never content.

        A view that reads somebody else's information puts `subjects` here, so the log can
        say whose it was.
        """
        return self.__dict__.setdefault("_audit_detail", {})

    def audit_subjects(self, user_ids):
        self.audit_detail["subjects"] = sorted({str(user_id) for user_id in user_ids})

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        principal = getattr(request, "auth", None)
        # Only calls that got as far as being somebody's are written down. A flood of
        # refused ones must not become a flood of rows, and a throttled call is by
        # definition one of a flood.
        if isinstance(principal, AgentPrincipal) and response.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
            audit.record(
                "api",
                request=request,
                grant=principal.grant,
                status_code=response.status_code,
                **self.audit_detail,
            )
        return response
