# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Where HR records are filed.

Every record here needs a workspace on it, because that is how the rest of the
product is shaped — but for HR that workspace carries no meaning. Nothing is ever
scoped by it, nothing is hidden behind it, and which one it is has no effect on
what anybody sees. The employment records, the hours and the figures belong to the
company as a whole.

So they are all filed in the same place, chosen once and used everywhere. Filing
them in whichever workspace somebody happened to be looking at would produce
records scattered across three workspaces that all have to be read together
anyway, and would invite somebody later to mistake that column for a boundary.
"""

# Django imports
from django.conf import settings

# Module imports
from plane.db.models import Workspace


def hr_home_workspace():
    """The workspace HR records are filed under.

    Named by setting where an installation wants to be explicit; otherwise the
    oldest workspace, which on a self-hosted installation is the company's own.
    """
    slug = getattr(settings, "HR_HOME_WORKSPACE_SLUG", "")
    if slug:
        named = Workspace.objects.filter(slug=slug).first()
        if named is not None:
            return named
    return Workspace.objects.order_by("created_at").first()


def hr_home_workspace_id():
    workspace = hr_home_workspace()
    return workspace.id if workspace else None
