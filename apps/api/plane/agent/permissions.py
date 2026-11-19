# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Scopes: what the person said yes to, enforced where the data is read."""

# Third-party imports
from rest_framework.permissions import BasePermission

# Module imports
from plane.agent.authentication import AgentPrincipal
from plane.agent.errors import insufficient_scope


class HasRequiredScope(BasePermission):
    """The view names the one scope it needs as `required_scope` (or one per method as `required_scopes`).

    A view that names none is refused rather than allowed: forgetting to say what a
    new endpoint needs must not turn it into one that needs nothing.
    """

    def has_permission(self, request, view):
        required = view.scope_for(request.method) if hasattr(view, "scope_for") else None
        principal = request.auth
        if required is None or not isinstance(principal, AgentPrincipal):
            return False
        if required not in principal.scopes:
            raise insufficient_scope(required)
        return True
