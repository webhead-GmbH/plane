# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Hours a settled month counted stop moving.

A month that has been handed in, approved or closed is never rebuilt again. Its
figures were read as they stood — approved, sent to payroll, invoiced on. So an
hour inside one cannot be edited or deleted afterwards: the month will not notice,
and the record and the figure would disagree with nothing saying which is right.

Moving an hour *out* of such a month is the damaging direction. The settled month
keeps counting it and the month it lands in counts it again, so the same hour is
paid and billed twice.
"""

# Python imports
from datetime import date, datetime, timedelta, timezone as utc
from uuid import uuid4

# Third party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import Issue, IssueWorkLog, State
from plane.hr.models import HrEmploymentProfile, HrPeriod
from plane.tests.factories import (
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    WorkspaceFactory,
    WorkspaceMemberFactory,
)

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

# Vienna in January is UTC+1, so 10:00 local is 09:00 UTC — comfortably inside the
# day either way, which keeps these tests about the lock and not about midnight.
IN_JANUARY = datetime(2026, 1, 20, 9, 0, tzinfo=utc.utc)
IN_FEBRUARY = datetime(2026, 2, 3, 9, 0, tzinfo=utc.utc)


@pytest.fixture
def person():
    return UserFactory(username=uuid4().hex)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def somewhere_to_work(user):
    workspace = WorkspaceFactory(owner=user)
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.ADMIN.value)
    project = ProjectFactory(workspace=workspace, created_by=user)
    ProjectMemberFactory(project=project, member=user, role=ROLE.ADMIN.value)
    state = State.objects.create(workspace=workspace, project=project, name="Doing", group="started")
    issue = Issue.objects.create(workspace=workspace, project=project, name="Something", state=state)
    return workspace, project, issue


def employed(user, workspace):
    return HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone="Europe/Vienna",
        hire_date=date(2024, 1, 1),
    )


def an_hour_on(user, workspace, project, issue, moment):
    return IssueWorkLog.objects.create(
        workspace=workspace,
        project=project,
        issue=issue,
        logged_by=user,
        duration=3600,
        started_at=moment,
    )


def month_of(profile, first, state):
    """A month in the given state.

    The figures are supplied because the database refuses to record a month as
    closed without the ones it was closed on — which is the whole reason those
    figures must stop moving afterwards.
    """
    return HrPeriod.objects.create(
        workspace=profile.workspace,
        profile=profile,
        period_start=first,
        period_end=date(first.year, first.month, 28),
        state=state,
        target_minutes=9240,
        actual_minutes=9240,
        balance_minutes=0,
    )


def worklog_url(workspace, project, issue, worklog):
    return (
        f"/api/workspaces/{workspace.slug}/projects/{project.id}"
        f"/issues/{issue.id}/worklogs/{worklog.id}/"
    )


class TestASettledMonthHoldsItsHours:
    def test_an_hour_in_a_closed_month_cannot_be_re_dated_into_an_open_one(self, person):
        """The double-billing case: January keeps it, February counts it again."""
        workspace, project, issue = somewhere_to_work(person)
        profile = employed(person, workspace)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.LOCKED)
        worked = an_hour_on(person, workspace, project, issue, IN_JANUARY)

        response = client_for(person).patch(
            worklog_url(workspace, project, issue, worked),
            {"started_at": IN_FEBRUARY.isoformat()},
            format="json",
        )

        assert response.status_code == 409
        worked.refresh_from_db()
        assert worked.started_at == IN_JANUARY

    def test_an_hour_cannot_be_moved_into_a_closed_month_either(self, person):
        """Arriving is the losing direction — the closed month will not be rebuilt."""
        workspace, project, issue = somewhere_to_work(person)
        profile = employed(person, workspace)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.LOCKED)
        worked = an_hour_on(person, workspace, project, issue, IN_FEBRUARY)

        response = client_for(person).patch(
            worklog_url(workspace, project, issue, worked),
            {"started_at": IN_JANUARY.isoformat()},
            format="json",
        )

        assert response.status_code == 409

    def test_its_length_cannot_be_changed_either(self, person):
        """Not only the date: the figure was read, whatever part of it moves."""
        workspace, project, issue = somewhere_to_work(person)
        profile = employed(person, workspace)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.LOCKED)
        worked = an_hour_on(person, workspace, project, issue, IN_JANUARY)

        response = client_for(person).patch(
            worklog_url(workspace, project, issue, worked),
            {"duration": 7200},
            format="json",
        )

        assert response.status_code == 409
        worked.refresh_from_db()
        assert worked.duration == 3600

    def test_it_cannot_be_deleted(self, person):
        workspace, project, issue = somewhere_to_work(person)
        profile = employed(person, workspace)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.LOCKED)
        worked = an_hour_on(person, workspace, project, issue, IN_JANUARY)

        response = client_for(person).delete(worklog_url(workspace, project, issue, worked))

        assert response.status_code == 409
        assert IssueWorkLog.objects.filter(pk=worked.pk).exists()

    def test_a_month_merely_handed_in_already_holds_its_hours(self, person):
        """The window opens at submitted, not at locked.

        A submitted month stops being rebuilt, so an hour edited out of one is
        just as lost as one edited out of a closed month — and the figures have
        already been put in front of somebody by then.
        """
        workspace, project, issue = somewhere_to_work(person)
        profile = employed(person, workspace)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.SUBMITTED)
        worked = an_hour_on(person, workspace, project, issue, IN_JANUARY)

        response = client_for(person).patch(
            worklog_url(workspace, project, issue, worked), {"duration": 7200}, format="json"
        )

        assert response.status_code == 409

    def test_a_reopened_month_lets_its_hours_be_corrected(self, person):
        """Reopening exists precisely so a correction can be made."""
        workspace, project, issue = somewhere_to_work(person)
        profile = employed(person, workspace)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.REOPENED)
        worked = an_hour_on(person, workspace, project, issue, IN_JANUARY)

        response = client_for(person).patch(
            worklog_url(workspace, project, issue, worked), {"duration": 7200}, format="json"
        )

        assert response.status_code == 200
        worked.refresh_from_db()
        assert worked.duration == 7200

    def test_an_open_month_is_untouched_by_any_of_this(self, person):
        workspace, project, issue = somewhere_to_work(person)
        profile = employed(person, workspace)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.OPEN)
        worked = an_hour_on(person, workspace, project, issue, IN_JANUARY)

        assert (
            client_for(person)
            .patch(worklog_url(workspace, project, issue, worked), {"duration": 7200}, format="json")
            .status_code
            == 200
        )

    def test_somebody_with_no_employment_record_is_not_stopped(self, person):
        """Plenty of people log hours here without their time being kept for them."""
        workspace, project, issue = somewhere_to_work(person)
        worked = an_hour_on(person, workspace, project, issue, IN_JANUARY)

        assert (
            client_for(person)
            .delete(worklog_url(workspace, project, issue, worked))
            .status_code
            == 204
        )

    def test_a_month_closed_in_another_workspace_still_holds_the_hour(self, person):
        """The ledger counts an hour wherever it was logged, so the lock reaches there too.

        The company is one company however many workspaces it keeps. An hour
        logged here fed the month closed over there, and editing it here would
        move a figure somebody has already signed off.
        """
        here = somewhere_to_work(person)
        elsewhere = WorkspaceFactory(owner=UserFactory(username=uuid4().hex))
        WorkspaceMemberFactory(workspace=elsewhere, member=person, role=ROLE.MEMBER.value)
        profile = employed(person, elsewhere)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.LOCKED)
        worked = an_hour_on(person, *here, IN_JANUARY)

        response = client_for(person).delete(worklog_url(*here, worked))

        assert response.status_code == 409

    def test_clearing_the_start_cannot_slide_it_into_a_closed_month(self, person):
        """The day follows the start, and the logged time when there is no start.

        Nothing in the payload says "February" here — the month moves because the
        field the day was read from went away, which is why the check is made
        against the row as the edit would leave it rather than against what was
        sent.
        """
        workspace, project, issue = somewhere_to_work(person)
        profile = employed(person, workspace)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.LOCKED)
        worked = IssueWorkLog.objects.create(
            workspace=workspace,
            project=project,
            issue=issue,
            logged_by=person,
            duration=3600,
            started_at=IN_FEBRUARY,
            logged_at=IN_JANUARY,
        )

        response = client_for(person).patch(
            worklog_url(workspace, project, issue, worked), {"started_at": None}, format="json"
        )

        assert response.status_code == 409

    def test_a_different_month_is_no_obstacle(self, person):
        """Only the month the hour is in, not every month the person has."""
        workspace, project, issue = somewhere_to_work(person)
        profile = employed(person, workspace)
        month_of(profile, date(2026, 1, 1), HrPeriod.State.LOCKED)
        worked = an_hour_on(person, workspace, project, issue, IN_FEBRUARY)

        response = client_for(person).patch(
            worklog_url(workspace, project, issue, worked),
            {"started_at": (IN_FEBRUARY + timedelta(days=1)).isoformat()},
            format="json",
        )

        assert response.status_code == 200
