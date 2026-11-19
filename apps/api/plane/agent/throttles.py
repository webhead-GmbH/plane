# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rate limits for connected apps.

Three layers, because each stops something the others do not: one person's link
cannot use more than its share (a loop in the app), one app cannot use more than
its share across everybody (a bug that affects all of them), and the endpoints that
anybody on the internet can reach are limited by where the call comes from.

DRF's default `AnonRateThrottle` does nothing for a caller that is authenticated, so
none of this is covered by the project-wide settings.
"""

# Third-party imports
from rest_framework.throttling import SimpleRateThrottle

# Module imports
from plane.agent import conf
from plane.agent.network import client_address


class GrantRateThrottle(SimpleRateThrottle):
    scope = "agent_grant"
    rate = conf.GRANT_RATE_LIMIT

    def get_cache_key(self, request, view):
        grant = getattr(request.auth, "grant", None)
        return f"throttle_agent_grant_{grant.id}" if grant is not None else None


class ClientRateThrottle(SimpleRateThrottle):
    scope = "agent_client"
    rate = conf.CLIENT_RATE_LIMIT

    def get_cache_key(self, request, view):
        client = getattr(request.auth, "client", None)
        return f"throttle_agent_client_{client.id}" if client is not None else None


class OAuthRateThrottle(SimpleRateThrottle):
    """For the endpoints that take a client secret, by the address the call comes from."""

    scope = "agent_oauth"
    rate = conf.OAUTH_RATE_LIMIT

    def get_cache_key(self, request, view):
        return f"throttle_agent_oauth_{client_address(request)}"


class ConsentRateThrottle(SimpleRateThrottle):
    """For the screens a signed-in person approves from, by person."""

    scope = "agent_consent"
    rate = "30/minute"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        return f"throttle_agent_consent_{user.pk}" if user is not None and user.is_authenticated else None
