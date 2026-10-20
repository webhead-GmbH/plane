# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""GET /api/hr/access/: whether the module has anything for somebody, and whether they run it.

Every other HR view refuses a person with no employment record, which is right for
them and wrong for this question: on the day the module goes live nobody has a
record, including the instance admin who has to create them all, and the web app
offered no way into Team time to that person.
"""

# Python imports
from datetime import date
from uuid import uuid4

# Third-party imports
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import HrEmploymentProfile
from plane.license.models import Instance, InstanceAdmin
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

URL = "/api/hr/access/"


def new_user():
    return UserFactory(username=uuid4().hex)


def access_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client.get(URL)


@pytest.fixture
def workspace():
    owner = new_user()
    workspace = WorkspaceFactory(owner=owner)
    WorkspaceMemberFactory(workspace=workspace, member=owner, role=ROLE.ADMIN.value)
    return workspace


def employ(workspace, user, is_hr_manager=False, is_active=True):
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.MEMBER.value)
    return HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone="Europe/Vienna",
        hire_date=date(2024, 1, 1),
        is_hr_manager=is_hr_manager,
        is_active=is_active,
    )


class TestHrAccess:
    def test_the_instance_admin_without_a_record_runs_the_module(self):
        user = new_user()
        instance = Instance.objects.first() or Instance.objects.create(
            instance_name="test", instance_id=uuid4().hex, current_version="1.0.0", last_checked_at=timezone.now()
        )
        InstanceAdmin.objects.create(instance=instance, user=user)

        response = access_for(user)

        assert response.status_code == 200
        assert response.data == {"is_employed": False, "is_hr_manager": True}

    def test_somebody_with_no_record_is_told_so_rather_than_refused(self):
        response = access_for(new_user())

        assert response.status_code == 200
        assert response.data == {"is_employed": False, "is_hr_manager": False}

    def test_an_employee(self, workspace):
        user = new_user()
        employ(workspace, user)

        assert access_for(user).data == {"is_employed": True, "is_hr_manager": False}

    def test_whoever_looks_after_the_team(self, workspace):
        user = new_user()
        employ(workspace, user, is_hr_manager=True)

        assert access_for(user).data == {"is_employed": True, "is_hr_manager": True}

    def test_somebody_who_has_left_no_longer_runs_anything(self, workspace):
        user = new_user()
        employ(workspace, user, is_hr_manager=True, is_active=False)

        assert access_for(user).data == {"is_employed": False, "is_hr_manager": False}

    def test_a_visitor_is_refused(self):
        assert APIClient().get(URL).status_code in (401, 403)
