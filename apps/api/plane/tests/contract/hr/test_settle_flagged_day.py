# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Answering for a day whose hours went missing.

A day is flagged when hours that were counted into it are no longer there, and a
month refuses to close while any day is flagged. The system will not guess
whether the hours were withdrawn on purpose or lost by accident, so somebody has
to say — and what they say is kept, because that sentence is what the closed
month is afterwards explained by.

Exercised through a real request rather than against the service, because for a
long time nothing reached this endpoint: it existed, the month refused to close,
and there was no way in the interface to answer the question it was asking.
"""

# Python imports
from datetime import date, datetime, timezone as utc
from uuid import uuid4

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import Issue, IssueWorkLog, State
from plane.hr.models import (
    HrAuditLog,
    HrContract,
    HrEmploymentProfile,
    HrPeriod,
    HrPeriodDay,
    HrWorkSchedule,
)
from plane.hr.services.ledger import rebuild_period
from plane.tests.factories import (
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    WorkspaceFactory,
    WorkspaceMemberFactory,
)

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

FULL = 462
MARCH = (2026, 3)
A_MONDAY = date(2026, 3, 2)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def manager():
    """Somebody who looks after the team, employed and able to see their own month."""
    user = UserFactory(username=uuid4().hex)
    workspace = WorkspaceFactory(owner=user)
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.ADMIN.value)
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone="Europe/Vienna",
        hire_date=date(2024, 1, 1),
        is_hr_manager=True,
    )
    HrContract.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2024, 1, 1),
        arrangement=HrContract.Arrangement.ONSITE_FULL_TIME,
        records_target_hours=True,
        weekly_minutes=2310,
    )
    HrWorkSchedule.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2024, 1, 1),
        monday_minutes=FULL,
        tuesday_minutes=FULL,
        wednesday_minutes=FULL,
        thursday_minutes=FULL,
        friday_minutes=FULL,
    )
    return user, profile


def a_day_whose_hours_went_missing(user, profile):
    """An hour counted into March, and then gone. Returns the flagged day."""
    project = ProjectFactory(workspace=profile.workspace, created_by=user)
    ProjectMemberFactory(project=project, member=user, role=ROLE.ADMIN.value)
    state = State.objects.create(workspace=profile.workspace, project=project, name="Doing", group="started")
    issue = Issue.objects.create(workspace=profile.workspace, project=project, name="Something", state=state)
    moment = datetime(2026, 3, 2, 9, 0, tzinfo=utc.utc)
    worklog = IssueWorkLog.objects.create(
        workspace=profile.workspace,
        project=project,
        issue=issue,
        logged_by=user,
        started_at=moment,
        logged_at=moment,
        duration=3600,
    )

    rebuild_period(profile, *MARCH)
    worklog.delete()
    rebuild_period(profile, *MARCH)

    period = HrPeriod.objects.get(profile_id=profile.id, period_start=date(2026, 3, 1))
    return period, HrPeriodDay.objects.get(period_id=period.id, work_date=A_MONDAY)


def settle_url(period, day):
    return f"/api/hr/periods/{period.id}/days/{day.id}/settle/"


class TestSettlingAFlaggedDay:
    def test_a_day_is_settled_with_a_note(self, manager):
        user, profile = manager
        period, day = a_day_whose_hours_went_missing(user, profile)
        assert day.needs_review is True

        response = client_for(user).post(
            settle_url(period, day),
            {"note": "Logged against the wrong work item and moved."},
            format="json",
        )

        assert response.status_code == 200
        day.refresh_from_db()
        assert day.needs_review is False
        assert day.note == "Logged against the wrong work item and moved."

    def test_an_empty_note_settles_nothing(self, manager):
        """The note is the whole point: the flag is a question, not a checkbox."""
        user, profile = manager
        period, day = a_day_whose_hours_went_missing(user, profile)

        response = client_for(user).post(settle_url(period, day), {"note": "   "}, format="json")

        assert response.status_code == 400
        day.refresh_from_db()
        assert day.needs_review is True

    def test_who_settled_it_and_why_is_written_down(self, manager):
        user, profile = manager
        period, day = a_day_whose_hours_went_missing(user, profile)

        client_for(user).post(settle_url(period, day), {"note": "Duplicate, removed on purpose."}, format="json")

        entry = HrAuditLog.objects.get(object_id=day.id, action="review_settled")
        assert entry.actor_id == user.id
        assert entry.reason == "Duplicate, removed on purpose."
        assert entry.changes["date"] == A_MONDAY.isoformat()

    def test_a_colleague_cannot_answer_for_somebody_else_s_day(self, manager):
        """The boundary that exists here is the role, not the workspace.

        Whoever looks after the team sees everybody, deliberately and across every
        workspace — employment is with the company, however many workspaces it
        keeps. An ordinary colleague sees only themselves, and a flagged day is
        reachable only through a month the caller may read, so somebody else's is
        simply not there.
        """
        user, profile = manager
        period, day = a_day_whose_hours_went_missing(user, profile)

        colleague = UserFactory(username=uuid4().hex)
        WorkspaceMemberFactory(workspace=profile.workspace, member=colleague, role=ROLE.MEMBER.value)
        HrEmploymentProfile.objects.create(
            workspace=profile.workspace,
            member=colleague,
            timezone="Europe/Vienna",
            hire_date=date(2024, 1, 1),
        )

        response = client_for(colleague).post(settle_url(period, day), {"note": "Not mine to answer."}, format="json")

        assert response.status_code in (403, 404)
        day.refresh_from_db()
        assert day.needs_review is True

    def test_somebody_with_no_employment_record_cannot_answer_either(self, manager):
        """A workspace member who is not employed through the module has no month."""
        user, profile = manager
        period, day = a_day_whose_hours_went_missing(user, profile)

        outsider = UserFactory(username=uuid4().hex)
        WorkspaceMemberFactory(workspace=profile.workspace, member=outsider, role=ROLE.MEMBER.value)

        response = client_for(outsider).post(settle_url(period, day), {"note": "Nothing to do with me."}, format="json")

        assert response.status_code in (403, 404)
        day.refresh_from_db()
        assert day.needs_review is True

    def test_the_flagged_days_are_readable_before_they_are_settled(self, manager):
        """What the screen asks for first: which days, and what they now come to."""
        user, profile = manager
        period, day = a_day_whose_hours_went_missing(user, profile)

        response = client_for(user).get(f"/api/hr/periods/{period.id}/days/")

        assert response.status_code == 200
        flagged = [row for row in response.json() if row["needs_review"]]
        assert [row["id"] for row in flagged] == [str(day.id)]
        assert flagged[0]["work_date"] == A_MONDAY.isoformat()
