# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who the app is talking to."""

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.agent.scopes import PROFILE, describe
from plane.agent.views.base import AgentAPIView
from plane.app.permissions import ROLE
from plane.db.models import WorkspaceMember

ROLE_NAMES = {ROLE.ADMIN.value: "admin", ROLE.MEMBER.value: "member", ROLE.GUEST.value: "guest"}


class MeEndpoint(AgentAPIView):
    """The person, the workspaces they belong to, and what this connection may do."""

    required_scope = PROFILE

    def get(self, request):
        user = request.user
        grant = self.grant
        memberships = (
            WorkspaceMember.objects.filter(member=user, is_active=True, workspace__deleted_at__isnull=True)
            .select_related("workspace")
            .order_by("workspace__name")
        )
        return Response(
            {
                "id": str(user.id),
                "display_name": user.display_name,
                "first_name": user.first_name,
                "last_name": user.last_name,
                # The person's own setting. Which day counts for their hours is decided
                # by their employment record and reported with the day (see `me/day`).
                "timezone": user.user_timezone,
                "workspaces": [
                    {
                        "slug": member.workspace.slug,
                        "name": member.workspace.name,
                        "role": ROLE_NAMES.get(member.role, "guest"),
                    }
                    for member in memberships
                ],
                "connection": {
                    "id": str(grant.id),
                    "scopes": describe(grant.scopes),
                    "created_at": grant.created_at.isoformat(),
                    "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
                    "account": {
                        "provider": grant.account_provider,
                        "id": grant.account_id,
                        "username": grant.account_username,
                        "name": grant.account_name,
                    },
                },
            },
            status=status.HTTP_200_OK,
        )
