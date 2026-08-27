# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who may see whose figures.

Two roles, because at this size there are two: you look at your own record, or you
look at everyone's. There is no team scoping, because there are no teams — a
branch for it would be code that never runs and still has to be kept correct.

The role lives on the employment profile rather than on workspace membership. The
membership role is shared with the wider product and is not ours to extend, and it
does not divide along the right line anyway: somebody engaged on a single project
may legitimately administer that project while having no business seeing anyone
else's hours.

Workspace administrators are treated as managers. They can already grant
themselves the flag, so withholding it would buy nothing; the point of the
separation is that looking is recorded, not that it is prevented.
"""

# Python imports
from functools import wraps

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import WorkspaceMember
from plane.hr.models import HrEmploymentProfile

SELF = "SELF"
MANAGER = "MANAGER"

_DENIED = {"error": "You don't have the required permissions."}


def _workspace_role(user, slug):
    """The caller's role in the workspace, or None if they are not an active member."""
    return (
        WorkspaceMember.objects.filter(member=user, workspace__slug=slug, is_active=True)
        .values_list("role", flat=True)
        .first()
    )


def resolve_hr_context(request, slug):
    """Work out who is asking and what they are allowed to see.

    Returns ``(profile, is_manager)``. The profile may be None for a workspace
    administrator who has no employment record of their own, which is a normal
    state — somebody can administer the workspace without being employed through it.
    """
    role = _workspace_role(request.user, slug)
    if role is None:
        return None, False

    profile = (
        HrEmploymentProfile.objects.filter(member=request.user, workspace__slug=slug)
        .select_related("workspace")
        .first()
    )
    is_manager = role == ROLE.ADMIN.value or bool(profile and profile.is_hr_manager)
    return profile, is_manager


def hr_permission(scope=SELF):
    """Gate a view on HR visibility.

    ``SELF`` lets somebody act on their own record, and on anyone else's only if
    they are a manager. ``MANAGER`` requires the manager role outright.

    On success the resolved profile and manager flag are attached to the request,
    so a view never has to repeat the lookup.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(instance, request, *args, **kwargs):
            slug = kwargs.get("slug")
            profile, is_manager = resolve_hr_context(request, slug)

            if profile is None and not is_manager:
                return Response(_DENIED, status=status.HTTP_403_FORBIDDEN)
            if scope == MANAGER and not is_manager:
                return Response(_DENIED, status=status.HTTP_403_FORBIDDEN)

            request.hr_profile = profile
            request.hr_is_manager = is_manager
            return view_func(instance, request, *args, **kwargs)

        return _wrapped

    return decorator


def visible_profiles(request, slug):
    """The employment records this caller may read.

    Every list view goes through here, so the rule about who can see whom lives in
    one place and can be tested on its own rather than being restated at each
    endpoint — which is how such a rule ends up applied inconsistently.
    """
    is_manager = getattr(request, "hr_is_manager", False)
    base = HrEmploymentProfile.objects.filter(workspace__slug=slug)
    if is_manager:
        return base
    profile = getattr(request, "hr_profile", None)
    if profile is None:
        return base.none()
    return base.filter(pk=profile.pk)


def readable_profile_or_none(request, slug, profile_id):
    """One record, if this caller may read it."""
    if profile_id is None:
        return getattr(request, "hr_profile", None)
    return visible_profiles(request, slug).filter(pk=profile_id).first()


def can_approve(request, profile):
    """Whether this caller may approve something belonging to that person.

    Approving your own absence or your own month is not a decision, so it is
    refused even for a manager. Where somebody is the only person who could
    approve anything, that is an organisational problem rather than one the module
    should paper over.
    """
    if not getattr(request, "hr_is_manager", False):
        return False
    own = getattr(request, "hr_profile", None)
    return not (own is not None and own.pk == profile.pk)
