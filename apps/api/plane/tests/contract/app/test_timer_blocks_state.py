# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A running timer keeps its work item out of states where time is not tracked.

Moving the work item to Done with a timer still going would leave the timer
counting hours against something finished. The move is refused with a reason the
client can put in the reader's language, rather than a sentence only in English.
"""

# Python imports
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


@pytest.fixture
def work():
    person = UserFactory(username=uuid4().hex)
    workspace = WorkspaceFactory(owner=person)
    WorkspaceMemberFactory(workspace=workspace, member=person, role=ROLE.ADMIN.value)
    project = ProjectFactory(workspace=workspace, project_lead=person)
    ProjectMemberFactory(project=project, member=person, role=ROLE.ADMIN.value)
    started = State.objects.create(workspace=workspace, project=project, name="In progress", group="started")
    done = State.objects.create(workspace=workspace, project=project, name="Done", group="completed")
    issue = Issue.objects.create(workspace=workspace, project=project, name="Something to do", state=started)
    IssueAssignee.objects.create(workspace=workspace, project=project, issue=issue, assignee=person)
    client = APIClient()
    client.force_authenticate(user=person)
    url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/"
    return {"person": person, "issue": issue, "done": done, "client": client, "url": url}


def run_timer(work):
    issue = work["issue"]
    return IssueWorkLog.objects.create(
        workspace=issue.workspace,
        project=issue.project,
        issue=issue,
        logged_by=work["person"],
        started_at=timezone.now(),
    )


class TestTimerKeepsTheWorkItemOpen:
    def test_moving_to_done_with_a_timer_running_is_refused_with_a_reason(self, work):
        run_timer(work)
        response = work["client"].patch(work["url"], {"state_id": str(work["done"].id)}, format="json")
        assert response.status_code == 400
        assert response.json()["reason"] == "timer_running"
        work["issue"].refresh_from_db()
        assert work["issue"].state_id != work["done"].id

    def test_with_no_timer_running_it_moves(self, work):
        response = work["client"].patch(work["url"], {"state_id": str(work["done"].id)}, format="json")
        assert response.status_code == 204
        work["issue"].refresh_from_db()
        assert work["issue"].state_id == work["done"].id
