# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who a connected app is acting for, decided afresh on every call.

Nothing about a token is trusted because it was valid last time. Each request looks
the token up and checks, then and there, that it has not expired or been revoked,
that the link it belongs to is still in force, that the app has not been switched
off and that the person has not been deactivated. Ending a connection therefore
takes effect on the very next call, not when some cache runs out.

These tokens are accepted by the connected-app endpoints and by nothing else, and
those endpoints accept nothing else. A token that leaks can reach what its scopes
name and no more: it cannot be turned into a browser session or an API key.
"""

# Django imports
from django.utils import timezone

# Third-party imports
from rest_framework.authentication import BaseAuthentication, get_authorization_header

# Module imports
from plane.agent import conf
from plane.agent.errors import invalid_token
from plane.agent.models import AgentGrant, AgentToken
from plane.agent.tokens import ACCESS_PREFIX, hash_secret


class AgentPrincipal:
    """What `request.auth` holds on a connected-app call."""

    def __init__(self, grant, token):
        self.grant = grant
        self.token = token
        self.client = grant.client
        self.scopes = frozenset(grant.scopes or [])


class AgentTokenAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer realm="plane-agent"'

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"bearer":
            return None
        if len(parts) != 2:
            raise invalid_token()
        try:
            presented = parts[1].decode("ascii")
        except UnicodeDecodeError:
            raise invalid_token()
        if not presented.startswith(ACCESS_PREFIX):
            raise invalid_token()

        token = (
            AgentToken.objects.select_related("grant", "grant__user", "grant__client")
            .filter(token_hash=hash_secret(presented), kind=AgentToken.ACCESS)
            .first()
        )
        now = timezone.now()
        if token is None or token.revoked_at is not None or token.expires_at <= now:
            raise invalid_token()

        grant = token.grant
        if not grant.is_usable(now) or not grant.client.is_active or not grant.user.is_active:
            raise invalid_token()

        self._touch(grant, now)
        return grant.user, AgentPrincipal(grant, token)

    @staticmethod
    def _touch(grant, now):
        if grant.last_used_at is None or now - grant.last_used_at > conf.LAST_USED_RESOLUTION:
            AgentGrant.objects.filter(pk=grant.pk).update(last_used_at=now)
