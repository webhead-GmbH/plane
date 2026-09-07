# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Handing over the team, and the two ways that went wrong quietly.

The flag on an employment record that says somebody looks after the team is the
widest grant in this module: `visible_profiles` returns every profile in the
installation for anybody who has it, deliberately — employment is with the
company, however many workspaces it keeps. So one checkbox hands over everyone's
hours, everyone's absences, and the reasons for them.

Two things were missing around it. It was written down nowhere, unlike every
other change to somebody's record. And nothing stopped the only person who had it
from taking it off themselves, after which no request reaches any of it and the
flag can only be put back from the database.
"""

# Python imports
from datetime import date
from uuid import uuid4

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import HrAuditLog, HrEmploymentProfile
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def new_user():
    return UserFactory(username=uuid4().hex)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def workspace():
    owner = new_user()
    workspace = WorkspaceFactory(owner=owner)
    WorkspaceMemberFactory(workspace=workspace, member=owner, role=ROLE.ADMIN.value)
    return workspace


def employ(workspace, is_hr_manager=False):
    user = new_user()
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.MEMBER.value)
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone="Europe/Vienna",
        hire_date=date(2024, 1, 1),
        is_hr_manager=is_hr_manager,
    )
    return user, profile


def profile_url(profile):
    return f"/api/hr/employees/{profile.id}/"


class TestHandingOverTheTeam:
    def test_granting_it_is_written_down(self, workspace):
        manager_user, _ = employ(workspace, is_hr_manager=True)
        _, colleague = employ(workspace)

        response = client_for(manager_user).patch(profile_url(colleague), {"is_hr_manager": True}, format="json")

        assert response.status_code == 200
        entry = HrAuditLog.objects.get(object_id=colleague.id, action="hr_manager_granted")
        assert entry.actor_id == manager_user.id
        assert entry.changes["is_hr_manager"] == {"from": False, "to": True}

    def test_withdrawing_it_is_written_down_too(self, workspace):
        manager_user, _ = employ(workspace, is_hr_manager=True)
        _, other = employ(workspace, is_hr_manager=True)

        client_for(manager_user).patch(profile_url(other), {"is_hr_manager": False}, format="json")

        entry = HrAuditLog.objects.get(object_id=other.id, action="hr_manager_withdrawn")
        assert entry.changes["is_hr_manager"] == {"from": True, "to": False}

    def test_an_unrelated_edit_files_nothing_about_the_flag(self, workspace):
        """Only the change itself is worth an entry; every save is not."""
        manager_user, manager = employ(workspace, is_hr_manager=True)

        client_for(manager_user).patch(profile_url(manager), {"timezone": "Europe/Berlin"}, format="json")

        assert not HrAuditLog.objects.filter(action__in=["hr_manager_granted", "hr_manager_withdrawn"]).exists()


class TestTheLastOneCannotStepDown:
    def test_the_only_manager_cannot_take_it_off_themselves(self, workspace):
        """Otherwise nobody reaches the module and nobody can hand it back."""
        manager_user, manager = employ(workspace, is_hr_manager=True)
        employ(workspace)

        response = client_for(manager_user).patch(profile_url(manager), {"is_hr_manager": False}, format="json")

        assert response.status_code == 409
        assert response.json()["reason"] == "last_manager"
        manager.refresh_from_db()
        assert manager.is_hr_manager is True

    def test_once_somebody_else_has_it_they_can(self, workspace):
        manager_user, manager = employ(workspace, is_hr_manager=True)
        _, successor = employ(workspace)

        client_for(manager_user).patch(profile_url(successor), {"is_hr_manager": True}, format="json")
        response = client_for(manager_user).patch(profile_url(manager), {"is_hr_manager": False}, format="json")

        assert response.status_code == 200
        manager.refresh_from_db()
        assert manager.is_hr_manager is False

    def test_a_manager_in_another_workspace_counts(self, workspace):
        """The flag reaches the whole installation, so the count has to as well.

        Refusing on account of "the last manager in this workspace" would be a
        wall in front of a company that has one somewhere else — and the one
        somewhere else can already read everything here.
        """
        manager_user, manager = employ(workspace, is_hr_manager=True)

        elsewhere = WorkspaceFactory(owner=new_user())
        employ(elsewhere, is_hr_manager=True)

        response = client_for(manager_user).patch(profile_url(manager), {"is_hr_manager": False}, format="json")

        assert response.status_code == 200

    def test_the_only_manager_cannot_be_marked_as_having_left(self, workspace):
        """The same lockout, reached through a field that looks unrelated.

        The guard watched `is_hr_manager` and `is_active` sat next to it on the
        same form. Marking the only manager as having left removes them from the
        `is_active=True` lookup that resolves the flag, so nobody is a manager
        and the endpoint that would put it back is manager-only.
        """
        manager_user, manager = employ(workspace, is_hr_manager=True)
        employ(workspace)

        response = client_for(manager_user).patch(profile_url(manager), {"is_active": False}, format="json")

        assert response.status_code == 409
        assert response.json()["reason"] == "last_manager"
        manager.refresh_from_db()
        assert manager.is_active is True

    def test_the_only_manager_cannot_be_removed_either(self, workspace):
        """Delete marks somebody as having left, so it is the same door again."""
        manager_user, manager = employ(workspace, is_hr_manager=True)
        employ(workspace)

        response = client_for(manager_user).delete(profile_url(manager))

        assert response.status_code == 409
        manager.refresh_from_db()
        assert manager.is_active is True

    def test_a_manager_who_cannot_sign_in_is_not_cover(self, workspace):
        """An employment record outlives the account it belongs to.

        Deactivating a Plane account leaves the HR record active and untouched,
        so counting it as cover hands the team to somebody the sign-in page
        refuses. It is the same reason somebody who has left does not count.
        """
        manager_user, manager = employ(workspace, is_hr_manager=True)
        other_user, _ = employ(workspace, is_hr_manager=True)
        other_user.is_active = False
        other_user.save(update_fields=["is_active"])

        response = client_for(manager_user).patch(profile_url(manager), {"is_hr_manager": False}, format="json")

        assert response.status_code == 409
        assert response.json()["reason"] == "last_manager"

    def test_somebody_who_has_left_does_not_count_as_cover(self, workspace):
        """They cannot sign in, so they are not somebody the module can fall back on."""
        manager_user, manager = employ(workspace, is_hr_manager=True)
        _, gone = employ(workspace, is_hr_manager=True)
        gone.is_active = False
        gone.save(update_fields=["is_active"])

        response = client_for(manager_user).patch(profile_url(manager), {"is_hr_manager": False}, format="json")

        assert response.status_code == 409
        assert response.json()["reason"] == "last_manager"
