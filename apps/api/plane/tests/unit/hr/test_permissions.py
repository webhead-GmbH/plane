# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who may see whose figures.

These are worth pinning tightly. Getting visibility wrong here does not produce a
broken page — it produces one colleague reading another's sick leave.
"""

# Python imports
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

# Django imports
from django.utils import timezone

# Third-party imports
import pytest

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import WorkspaceMember
from plane.hr.models import HrEmploymentProfile
from plane.license.models import Instance, InstanceAdmin
from plane.hr.permissions import (
    can_approve,
    readable_profile_or_none,
    resolve_hr_context,
    visible_profiles,
)
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def new_user():
    """A user with a distinct username.

    The shared factory leaves ``username`` unset, and it is unique, so a second
    user in the same test collides on the empty string.
    """
    return UserFactory(username=uuid4().hex)


@pytest.fixture
def workspace():
    owner = new_user()
    workspace = WorkspaceFactory(owner=owner)
    WorkspaceMemberFactory(workspace=workspace, member=owner, role=ROLE.ADMIN.value)
    return workspace


def add_person(workspace, role=ROLE.MEMBER.value, is_hr_manager=False, with_profile=True):
    user = new_user()
    WorkspaceMemberFactory(workspace=workspace, member=user, role=role)
    profile = None
    if with_profile:
        profile = HrEmploymentProfile.objects.create(
            workspace=workspace,
            member=user,
            hire_date=date(2024, 1, 1),
            is_hr_manager=is_hr_manager,
        )
    return user, profile


def make_instance_admin(user):
    """Somebody who administers the installation rather than any workspace."""
    instance = Instance.objects.first() or Instance.objects.create(
        instance_name="test",
        instance_id=uuid4().hex,
        current_version="1.0.0",
        last_checked_at=timezone.now(),
    )
    InstanceAdmin.objects.create(instance=instance, user=user)
    return user


def request_for(user):
    return SimpleNamespace(user=user)


def prepared(user):
    """A request that has been through the decorator."""
    request = request_for(user)
    profile, is_manager = resolve_hr_context(request)
    request.hr_profile = profile
    request.hr_is_manager = is_manager
    return request


class TestContextResolution:
    def test_an_ordinary_employee_is_not_a_manager(self, workspace):
        user, profile = add_person(workspace)
        resolved, is_manager = resolve_hr_context(request_for(user))
        assert resolved == profile
        assert is_manager is False

    def test_the_flag_makes_someone_a_manager_without_touching_their_workspace_role(
        self, workspace
    ):
        user, _ = add_person(workspace, is_hr_manager=True)
        _, is_manager = resolve_hr_context(request_for(user))
        assert is_manager is True
        assert (
            WorkspaceMember.objects.get(workspace=workspace, member=user).role == ROLE.MEMBER.value
        )

    def test_administering_a_workspace_does_not_make_you_a_manager(self, workspace):
        # Anybody can create a workspace. If that were enough, creating one would
        # be enough to read everyone's sick leave.
        _, is_manager = resolve_hr_context(request_for(workspace.owner))
        assert is_manager is False

    def test_an_instance_administrator_is_a_manager_without_being_employed(self, workspace):
        # The one authority that does not come from an employment record, and so
        # the only way in before the first one exists.
        profile, is_manager = resolve_hr_context(request_for(make_instance_admin(new_user())))
        assert profile is None
        assert is_manager is True

    def test_somebody_with_no_employment_record_gets_nothing(self, workspace):
        outsider = new_user()
        profile, is_manager = resolve_hr_context(request_for(outsider))
        assert profile is None
        assert is_manager is False

    def test_somebody_who_has_left_gets_nothing(self, workspace):
        # Their months stay readable to a manager; their own way in does not.
        user, profile = add_person(workspace)
        HrEmploymentProfile.objects.filter(pk=profile.pk).update(is_active=False)
        resolved, is_manager = resolve_hr_context(request_for(user))
        assert resolved is None
        assert is_manager is False

    def test_a_deactivated_workspace_membership_changes_nothing(self, workspace):
        # Employment is with the company, not with a workspace. Somebody removed
        # from one workspace is still employed and still has a month to report.
        user, profile = add_person(workspace)
        WorkspaceMember.objects.filter(workspace=workspace, member=user).update(is_active=False)
        resolved, _ = resolve_hr_context(request_for(user))
        assert resolved == profile


class TestVisibility:
    def test_an_employee_sees_only_themselves(self, workspace):
        user, profile = add_person(workspace)
        add_person(workspace)
        add_person(workspace)
        visible = visible_profiles(prepared(user))
        assert list(visible) == [profile]

    def test_a_manager_sees_everyone(self, workspace):
        manager_user, _ = add_person(workspace, is_hr_manager=True)
        add_person(workspace)
        add_person(workspace)
        visible = visible_profiles(prepared(manager_user))
        assert visible.count() == 3

    def test_a_manager_sees_people_filed_under_any_workspace(self, workspace):
        # The workspaces are one company. Somebody whose employment record happens
        # to be filed under another one is still a colleague with a month to close.
        manager_user, _ = add_person(workspace, is_hr_manager=True)
        other = WorkspaceFactory(owner=new_user())
        add_person(other)
        visible = visible_profiles(prepared(manager_user))
        assert visible.count() == 2

    def test_an_outsider_sees_nothing(self, workspace):
        add_person(workspace)
        outsider = new_user()
        visible = visible_profiles(prepared(outsider))
        assert visible.count() == 0

    def test_an_employee_cannot_read_a_colleague_by_asking_for_them_directly(self, workspace):
        user, _ = add_person(workspace)
        _, colleague = add_person(workspace)
        found = readable_profile_or_none(prepared(user), colleague.id)
        assert found is None

    def test_a_manager_can_read_a_colleague_directly(self, workspace):
        manager_user, _ = add_person(workspace, is_hr_manager=True)
        _, colleague = add_person(workspace)
        found = readable_profile_or_none(prepared(manager_user), colleague.id
        )
        assert found == colleague

    def test_asking_for_nobody_in_particular_returns_your_own_record(self, workspace):
        user, profile = add_person(workspace)
        found = readable_profile_or_none(prepared(user), None)
        assert found == profile


class TestApproval:
    def test_an_employee_cannot_approve(self, workspace):
        user, profile = add_person(workspace)
        assert can_approve(prepared(user), profile) is False

    def test_a_manager_can_approve_for_someone_else(self, workspace):
        manager_user, _ = add_person(workspace, is_hr_manager=True)
        _, colleague = add_person(workspace)
        assert can_approve(prepared(manager_user), colleague) is True

    def test_a_manager_cannot_approve_their_own(self, workspace):
        # Approving your own month is not a decision.
        manager_user, manager_profile = add_person(workspace, is_hr_manager=True)
        assert can_approve(prepared(manager_user), manager_profile) is False
