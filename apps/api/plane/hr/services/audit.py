# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who changed which hour record, when, from what to what, and why.

Hours here are freely editable by the person they belong to and by whoever looks
after the team. That is the right arrangement — people correct their own
mistakes — but it means every figure this module produces is only as good as the
trail behind it. Without one, a month that came to 142 hours and now comes to 138
has no answer to the only question worth asking about the difference.

Kept as a plain record of the change rather than as a version of the row. The
question people actually ask is "what happened to this", and a list of changes
answers it directly, whereas a pile of snapshots has to be diffed first.

Written on the way out of a request, after the change has been made, so a refused
change leaves nothing behind. Failing to write the entry never fails the request:
losing the hour record because its history could not be filed would be the worse
of the two outcomes.
"""

# Python imports
import logging
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

# Module imports
from plane.hr.models import HrAuditLog

logger = logging.getLogger("plane.hr")


def readable(value):
    """A value the JSON column can hold and a person can read a year later."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    return str(value)


def snapshot(instance, fields):
    """The fields of a row as they stand, for comparing against afterwards."""
    return {field: readable(getattr(instance, field, None)) for field in fields}


def differences(before, after):
    """Only what actually moved, as from/to pairs.

    Recording the untouched fields as well would bury the one that changed, which
    is the field somebody opened the entry to find.
    """
    return {
        field: {"from": before.get(field), "to": after.get(field)}
        for field in after
        if before.get(field) != after.get(field)
    }


def record(profile, actor, obj, action, changes=None, reason="", request=None, object_id=None):
    """File one change against the person it was about.

    The person the change was about is not always the person who made it — that
    distinction is the reason the table has both — so the profile is passed in
    rather than read from whoever is signed in.

    ``object_id`` is for the one case the object cannot answer for itself. Django
    clears the primary key on a deleted instance, so filing the entry afterwards —
    which is the only order that can say the deletion happened — recorded no id at
    all. A deletion is the change the row can no longer testify to, so it is the
    one where losing the id costs the most: the entry says something was removed
    and nothing about which thing.
    """
    try:
        HrAuditLog.objects.create(
            workspace_id=profile.workspace_id,
            profile_id=profile.id,
            actor=actor if actor is not None and not getattr(actor, "is_anonymous", False) else None,
            actor_email=getattr(actor, "email", "") or "",
            object_type=obj.__class__.__name__,
            object_id=object_id if object_id is not None else getattr(obj, "id", None),
            action=action,
            changes=changes or {},
            reason=reason or "",
            request_id=getattr(request, "request_id", "") or "" if request is not None else "",
        )
    except Exception:
        # An hour record that was saved but whose history could not be filed is
        # worse recorded than it was; an hour record refused because of the same
        # failure is not recorded at all.
        logger.exception(
            "Could not file an HR audit entry for %s %s",
            action,
            object_id if object_id is not None else getattr(obj, "id", None),
        )
