# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""One person, one timer, wherever they are.

The workspaces on this installation all belong to one company, and somebody can
be working in any of them. Nobody works on two things at the same instant, so
starting a timer anywhere has to stop whatever was already running — including a
timer left going in a workspace they have since navigated away from.

Getting this wrong is not a display problem. A timer that keeps running in the
workspace somebody left accrues hours against a work item they stopped touching,
and those hours reach both the month's figures and the customer's invoice.
"""

# Python imports
from datetime import timedelta
from uuid import uuid4

# Django imports
from django.utils import timezone

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import Issue, IssueAssignee, IssueWorkLog, State
from plane.tests.factories import (
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    WorkspaceFactory,
    WorkspaceMemberFactory,
)

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def a_place_to_work(person):
    """A workspace, project and assigned work item with a timer-eligible state."""
    workspace = WorkspaceFactory(owner=person)
    WorkspaceMemberFactory(workspace=workspace, member=person, role=ROLE.ADMIN.value)
    project = ProjectFactory(workspace=workspace, project_lead=person)
    ProjectMemberFactory(project=project, member=person, role=ROLE.ADMIN.value)

    state = State.objects.create(
        workspace=workspace, project=project, name="In progress", group="started"
    )
    issue = Issue.objects.create(
        workspace=workspace, project=project, name="Something to do", state=state
    )
    IssueAssignee.objects.create(
        workspace=workspace, project=project, issue=issue, assignee=person
    )
    return workspace, project, issue


def timer_url(workspace, project, issue):
    return (
        f"/api/workspaces/{workspace.slug}/projects/{project.id}"
        f"/issues/{issue.id}/timer/"
    )


@pytest.fixture
def person():
    return UserFactory(username=uuid4().hex)


class TestOneTimerPerPerson:
    def test_starting_a_timer_stops_one_running_in_another_workspace(self, person):
        first_workspace, first_project, first_issue = a_place_to_work(person)
        second_workspace, second_project, second_issue = a_place_to_work(person)
        assert first_workspace.id != second_workspace.id

        client = client_for(person)
        started = client.post(timer_url(first_workspace, first_project, first_issue))
        assert started.status_code == 201

        # Wind the first timer back so the length it is closed at is unambiguous.
        IssueWorkLog.objects.filter(issue=first_issue).update(
            started_at=timezone.now() - timedelta(minutes=30)
        )

        moved_on = client.post(timer_url(second_workspace, second_project, second_issue))
        assert moved_on.status_code == 201

        first = IssueWorkLog.objects.get(issue=first_issue)
        assert first.duration is not None, "the timer left behind is still running"
        assert 29 * 60 <= first.duration <= 31 * 60, "it was closed at the time it ran"

        second = IssueWorkLog.objects.get(issue=second_issue)
        assert second.duration is None, "the new timer is the one running"

    def test_only_ever_one_timer_is_running_anywhere(self, person):
        first_workspace, first_project, first_issue = a_place_to_work(person)
        second_workspace, second_project, second_issue = a_place_to_work(person)
        third_workspace, third_project, third_issue = a_place_to_work(person)

        client = client_for(person)
        for workspace, project, issue in (
            (first_workspace, first_project, first_issue),
            (second_workspace, second_project, second_issue),
            (third_workspace, third_project, third_issue),
        ):
            client.post(timer_url(workspace, project, issue))

        running = IssueWorkLog.objects.filter(logged_by=person, duration__isnull=True)
        assert running.count() == 1
        assert running.first().issue_id == third_issue.id

    def test_the_hours_from_the_workspace_left_behind_are_kept(self, person):
        # Stopping the timer must not discard what was worked. Those minutes belong
        # in the month, and in whatever the customer is billed.
        first_workspace, first_project, first_issue = a_place_to_work(person)
        second_workspace, second_project, second_issue = a_place_to_work(person)

        client = client_for(person)
        client.post(timer_url(first_workspace, first_project, first_issue))
        IssueWorkLog.objects.filter(issue=first_issue).update(
            started_at=timezone.now() - timedelta(hours=2)
        )
        client.post(timer_url(second_workspace, second_project, second_issue))

        kept = IssueWorkLog.objects.get(issue=first_issue)
        assert kept.workspace_id == first_workspace.id, "still filed where it was worked"
        assert kept.duration >= 2 * 60 * 60 - 60

    def test_one_persons_timer_does_not_stop_somebody_elses(self, person):
        # The rule is about one person being in one place, not about the workspace.
        colleague = UserFactory(username=uuid4().hex)
        workspace, project, issue = a_place_to_work(person)

        WorkspaceMemberFactory(workspace=workspace, member=colleague, role=ROLE.MEMBER.value)
        ProjectMemberFactory(project=project, member=colleague, role=ROLE.MEMBER.value)
        IssueAssignee.objects.create(
            workspace=workspace, project=project, issue=issue, assignee=colleague
        )

        client_for(colleague).post(timer_url(workspace, project, issue))
        assert IssueWorkLog.objects.filter(
            logged_by=colleague, duration__isnull=True
        ).count() == 1

        elsewhere, its_project, its_issue = a_place_to_work(person)
        client_for(person).post(timer_url(elsewhere, its_project, its_issue))

        assert IssueWorkLog.objects.filter(
            logged_by=colleague, duration__isnull=True
        ).count() == 1, "somebody else starting work did not stop theirs"

    def test_a_timer_that_had_not_yet_run_a_second_still_counts_as_time(self, person):
        # Rounding an instant to zero would leave a worklog that is neither running
        # nor has a length, and nothing downstream expects that.
        first_workspace, first_project, first_issue = a_place_to_work(person)
        second_workspace, second_project, second_issue = a_place_to_work(person)

        client = client_for(person)
        client.post(timer_url(first_workspace, first_project, first_issue))
        client.post(timer_url(second_workspace, second_project, second_issue))

        assert IssueWorkLog.objects.get(issue=first_issue).duration >= 1
