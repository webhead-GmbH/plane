# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""One person, one timer, wherever they happen to be working.

The workspaces on this installation are one company. Somebody cannot be doing two
things at the same moment, so a timer started anywhere ends whatever was already
running — and the hour that was running still has to land in the month, not be
thrown away when the person moves to a different workspace and starts again.

Worth a test of its own because the rule is enforced in exactly one place, by the
absence of a workspace filter. A well-meaning "scope this query properly" change
would look like a correction and would silently break it.
"""

# Python imports
from datetime import date, timedelta
from uuid import uuid4

# Django imports
from django.utils import timezone

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import Issue, IssueAssignee, IssueWorkLog, State
from plane.hr.models import HrEmploymentProfile
from plane.hr.services.ledger import has_running_timer, period_totals, rebuild_period
from plane.hr.utils.calendar import hr_local_date
from plane.tests.factories import (
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    WorkspaceFactory,
    WorkspaceMemberFactory,
)

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.fixture
def person():
    return UserFactory(username=uuid4().hex)


def a_workspace_with_work_for(user):
    """A workspace, a project and an issue the person may start a timer on."""
    workspace = WorkspaceFactory(owner=user)
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.ADMIN.value)
    project = ProjectFactory(workspace=workspace, created_by=user)
    ProjectMemberFactory(project=project, member=user, role=ROLE.ADMIN.value)
    state = State.objects.create(
        workspace=workspace, project=project, name="In progress", group="started"
    )
    issue = Issue.objects.create(
        workspace=workspace, project=project, name="Something to do", state=state
    )
    IssueAssignee.objects.create(
        workspace=workspace, project=project, issue=issue, assignee=user
    )
    return workspace, project, issue


def employed(user):
    """An employment record, filed somewhere, belonging to nowhere in particular."""
    return HrEmploymentProfile.objects.create(
        workspace=WorkspaceFactory(owner=UserFactory(username=uuid4().hex)),
        member=user,
        timezone="Europe/Vienna",
        hire_date=date(2024, 1, 1),
    )


def timer_url(workspace, project, issue):
    return (
        f"/api/workspaces/{workspace.slug}/projects/{project.id}"
        f"/issues/{issue.id}/timer/"
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestOneTimerPerPerson:
    def test_starting_one_somewhere_else_stops_the_one_already_running(self, person):
        here = a_workspace_with_work_for(person)
        there = a_workspace_with_work_for(person)
        client = client_for(person)

        started = client.post(timer_url(*here))
        assert started.status_code == 201
        first = IssueWorkLog.objects.get(pk=started.json()["id"])
        assert first.duration is None

        second = client.post(timer_url(*there))
        assert second.status_code == 201

        first.refresh_from_db()
        assert first.duration is not None, "the timer in the other workspace kept running"
        assert IssueWorkLog.objects.filter(logged_by=person, duration__isnull=True).count() == 1

    def test_the_stopped_timer_keeps_its_minutes(self, person):
        # Stopping is not discarding. Those minutes were worked.
        here = a_workspace_with_work_for(person)
        there = a_workspace_with_work_for(person)
        client = client_for(person)

        started = client.post(timer_url(*here))
        first = IssueWorkLog.objects.get(pk=started.json()["id"])
        # Backdate the start so the elapsed time is a figure rather than a second.
        IssueWorkLog.objects.filter(pk=first.pk).update(
            started_at=timezone.now() - timedelta(hours=2)
        )

        client.post(timer_url(*there))

        first.refresh_from_db()
        assert first.duration >= 2 * 60 * 60

    def test_a_running_timer_is_visible_from_a_workspace_it_is_not_in(self, person):
        # The personal view is reached from wherever somebody happens to be, so it
        # has to report the timer that is actually running, not the one running here.
        profile = employed(person)
        today = hr_local_date(timezone.now(), "Europe/Vienna")
        elsewhere = a_workspace_with_work_for(person)
        assert has_running_timer(profile, today.year, today.month) is False
        client_for(person).post(timer_url(*elsewhere))
        assert has_running_timer(profile, today.year, today.month) is True

    def test_hours_from_every_workspace_land_in_the_same_month(self, person):
        # The point of the whole arrangement: one month, all of somebody's hours.
        profile = employed(person)
        client = client_for(person)
        for place in (a_workspace_with_work_for(person), a_workspace_with_work_for(person)):
            started = client.post(timer_url(*place))
            IssueWorkLog.objects.filter(pk=started.json()["id"]).update(
                started_at=timezone.now() - timedelta(hours=1), duration=3600
            )

        today = hr_local_date(timezone.now(), "Europe/Vienna")
        period = rebuild_period(profile, today.year, today.month)
        assert period_totals(period)["actual_minutes"] == 120
