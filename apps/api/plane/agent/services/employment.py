# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The HR record behind a connected person, and the day it is for them."""

# Django imports
from django.utils import timezone

# Module imports
from plane.hr.models import HrEmploymentProfile
from plane.hr.services.ledger import profile_timezone
from plane.hr.utils.calendar import hr_local_date, hr_timezone


def employment_for(user):
    """The person's active employment record, or None.

    None is a normal answer, not an error: an instance administrator, a contractor
    or a guest has none, and a connected app has to be told that plainly rather than
    refused, or it cannot tell "not employed here" from "something went wrong".
    """
    return HrEmploymentProfile.objects.filter(member=user, is_active=True).select_related("workspace").first()


def zone_name_for(user, profile):
    """The time zone this person's days are measured in, as a name."""
    name = profile_timezone(profile) if profile is not None else user.user_timezone
    return str(hr_timezone(name))


def today_for(user, profile):
    """Today's date where this person is."""
    name = profile_timezone(profile) if profile is not None else user.user_timezone
    return hr_local_date(timezone.now(), name)
