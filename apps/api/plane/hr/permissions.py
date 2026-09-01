# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who may see whose figures.

None of this is scoped to a workspace, and that is the point. The workspaces on
this installation all belong to one company and the people in them are the same
people, so employment, hours, leave and the monthly figures belong to the person
and the company — not to whichever workspace somebody happened to be looking at
when they opened the page. Everybody reaches the same records from anywhere.

Two roles, because at this size there are two: you look at your own record, or you
look at everyone's. There is no team scoping, because there are no teams — a
branch for it would be code that never runs and still has to be kept correct.

Being a manager is a property of the person, recorded on their employment record,
rather than something inferred from administering a workspace. Inferring it would
have meant that creating a workspace was enough to see everybody's sick leave.
Instance administrators also count, which is what makes the very first setup
possible before anybody has been given the flag.
"""

# Python imports
from functools import wraps

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.hr.models import HrEmploymentProfile
from plane.license.models import InstanceAdmin

SELF = "SELF"
MANAGER = "MANAGER"

_DENIED = {"error": "You don't have the required permissions."}


def is_instance_admin(user):
    """Whether somebody administers the installation itself.

    The only authority here that does not come from an employment record, and so
    the only one available before the first one exists.
    """
    if user is None or user.is_anonymous:
        return False
    return InstanceAdmin.objects.filter(user=user).exists()


def resolve_hr_context(request):
    """Work out who is asking and what they are allowed to see.

    Returns ``(profile, is_manager)``. The profile may be None for an instance
    administrator who is not employed here, which is a normal state.
    """
    user = request.user
    if user is None or user.is_anonymous:
        return None, False

    # Somebody who has left is marked inactive rather than removed, because the
    # months they worked still have to be readable by a manager. Their own way in
    # closes here: an inactive record is history, not an account.
    profile = HrEmploymentProfile.objects.filter(member=user, is_active=True).select_related("member").first()
    is_manager = bool(profile and profile.is_hr_manager) or is_instance_admin(user)
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
            profile, is_manager = resolve_hr_context(request)

            if profile is None and not is_manager:
                return Response(_DENIED, status=status.HTTP_403_FORBIDDEN)
            if scope == MANAGER and not is_manager:
                return Response(_DENIED, status=status.HTTP_403_FORBIDDEN)

            request.hr_profile = profile
            request.hr_is_manager = is_manager
            return view_func(instance, request, *args, **kwargs)

        return _wrapped

    return decorator


def visible_profiles(request):
    """The employment records this caller may read.

    Every list view goes through here, so the rule about who sees whom lives in
    one place and can be tested on its own. Restating it at each endpoint is how
    such a rule ends up applied inconsistently, and the failure mode is not a
    broken page — it is one colleague reading another's medical absence.
    """
    if getattr(request, "hr_is_manager", False):
        return HrEmploymentProfile.objects.all()

    profile = getattr(request, "hr_profile", None)
    if profile is None:
        return HrEmploymentProfile.objects.none()
    return HrEmploymentProfile.objects.filter(pk=profile.pk)


def readable_profile_or_none(request, profile_id):
    """One record, if this caller may read it."""
    if profile_id is None:
        return getattr(request, "hr_profile", None)
    return visible_profiles(request).filter(pk=profile_id).first()


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
