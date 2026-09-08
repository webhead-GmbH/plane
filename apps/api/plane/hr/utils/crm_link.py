# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""How a person here reaches their CRM staff account.

The worklog sync maps a Plane user to a CRM staff id one of two ways: the
``crm_staff_id`` set on their workspace membership, or failing that a match on
email address. The first is a decision somebody made; the second is a guess that
happens to be right most of the time, because both systems usually hold the same
address.

The guess is the problem this exists to make visible. When it fails there is
nothing on any screen to say so — the sync writes a line to the log and the
person's hours simply never become a CRM timer. Reporting which of the two is in
force, and whether either is, turns that into something the office can see and
put right.

Reading and writing both go through here so the answer shown on the screen cannot
drift away from the answer the sync arrives at.
"""

from plane.db.models import WorkspaceMember


def _memberships(profile):
    """Every active membership of the person, newest workspace first.

    The id belongs to a membership, so somebody in more than one workspace has
    more than one place to put it. On this installation the workspaces belong to
    one company and the same person is the same employee in all of them, so they
    are treated as one: a person has one CRM account, not one per workspace.
    """
    return WorkspaceMember.objects.filter(member_id=profile.member_id, is_active=True)


def crm_link_for(profile):
    """The staff id in force for this person, and where it came from.

    ``origin`` is "set" for an id somebody entered, "email" where the address is
    the only thing joining the two systems, and "none" where nothing does.
    """
    for member in _memberships(profile):
        if member.crm_staff_id:
            return {"staff_id": member.crm_staff_id, "origin": "set"}

    email = (getattr(profile.member, "email", "") or "").strip()
    return {"staff_id": None, "origin": "email" if email else "none"}


def set_crm_staff_id(profile, staff_id):
    """Record the CRM staff account this person's hours belong to.

    Written to every one of their memberships rather than one, because the id
    answers "who is this person in the CRM", which does not change between
    workspaces. Setting it in one place and not another would leave the sync
    guessing in the workspaces that were missed — the exact failure this is meant
    to remove.

    ``None`` clears it, which puts them back on the email match.
    """
    _memberships(profile).update(crm_staff_id=staff_id)
