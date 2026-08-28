# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The scheduled work: closing forgotten timers and keeping open months current."""

# Python imports
from datetime import date, timedelta
from uuid import uuid4

# Django imports
from django.utils import timezone

# Third-party imports
import pytest

# Module imports
from plane.db.models import Issue, IssueWorkLog, State
from plane.hr.bgtasks.ledger_rebuild import _recent_months, rebuild_open_periods
from plane.hr.bgtasks.timer_sweeper import AUTO_STOPPED_PREFIX, close_runaway_timers
from plane.hr.models import (
    HrAuditLog,
    HrContract,
    HrEmploymentProfile,
    HrPeriod,
    HrPeriodDay,
    HrWorkSchedule,
)
from plane.tests.factories import ProjectFactory, UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

FULL = 462


def new_user():
    return UserFactory(username=uuid4().hex)


@pytest.fixture
def profile():
    user = new_user()
    workspace = WorkspaceFactory(owner=user)
    WorkspaceMemberFactory(workspace=workspace, member=user)
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace, member=user, timezone="Europe/Vienna", hire_date=date(2024, 1, 1)
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
    return profile


@pytest.fixture
def issue(profile):
    project = ProjectFactory(workspace=profile.workspace, created_by=profile.member)
    state = State.objects.filter(project=project).first() or State.objects.create(
        name="Todo", project=project, workspace=profile.workspace, group="unstarted"
    )
    return Issue.objects.create(
        project=project, workspace=profile.workspace, name="A work item", state=state
    )


def running_timer(profile, issue, started_at):
    return IssueWorkLog.objects.create(
        workspace=profile.workspace,
        project_id=issue.project_id,
        issue=issue,
        logged_by=profile.member,
        started_at=started_at,
        logged_at=started_at,
        duration=None,
    )


class TestRunawayTimers:
    def test_a_timer_left_running_overnight_is_closed(self, profile, issue):
        worklog = running_timer(profile, issue, timezone.now() - timedelta(hours=40))
        assert close_runaway_timers() == 1
        worklog.refresh_from_db()
        assert worklog.duration == 600 * 60
        assert worklog.description.startswith(AUTO_STOPPED_PREFIX)

    def test_the_person_is_told_it_was_not_them(self, profile, issue):
        worklog = running_timer(profile, issue, timezone.now() - timedelta(hours=40))
        close_runaway_timers()
        entry = HrAuditLog.objects.get(action="timer_automatically_stopped")
        assert entry.object_id == worklog.id
        assert entry.changes["recorded_seconds"] == 600 * 60
        # The real elapsed time is written down even though it is not what was
        # recorded, so the person correcting it can see what they are correcting.
        assert entry.changes["elapsed_seconds"] > 600 * 60

    def test_a_timer_still_within_a_working_day_is_left_alone(self, profile, issue):
        worklog = running_timer(profile, issue, timezone.now() - timedelta(hours=3))
        assert close_runaway_timers() == 0
        worklog.refresh_from_db()
        assert worklog.duration is None

    def test_a_finished_entry_is_never_touched(self, profile, issue):
        worklog = running_timer(profile, issue, timezone.now() - timedelta(hours=40))
        worklog.duration = 3600
        worklog.save()
        assert close_runaway_timers() == 0
        worklog.refresh_from_db()
        assert worklog.duration == 3600

    def test_closing_twice_does_not_stack_the_note(self, profile, issue):
        worklog = running_timer(profile, issue, timezone.now() - timedelta(hours=40))
        close_runaway_timers()
        worklog.refresh_from_db()
        worklog.duration = None
        worklog.save()
        close_runaway_timers()
        worklog.refresh_from_db()
        assert worklog.description.count(AUTO_STOPPED_PREFIX) == 1

    def test_time_logged_by_somebody_outside_the_module_is_still_closed(self, issue):
        # No employment record to hang a note on, but the timer still has to stop —
        # it is blocking that person from starting another one.
        outsider = new_user()
        WorkspaceMemberFactory(workspace=issue.workspace, member=outsider)
        worklog = IssueWorkLog.objects.create(
            workspace=issue.workspace,
            project_id=issue.project_id,
            issue=issue,
            logged_by=outsider,
            started_at=timezone.now() - timedelta(hours=40),
            logged_at=timezone.now() - timedelta(hours=40),
            duration=None,
        )
        assert close_runaway_timers() == 1
        worklog.refresh_from_db()
        assert worklog.duration == 600 * 60


class TestScheduledRebuild:
    def test_open_months_are_brought_up_to_date(self, profile):
        assert not HrPeriod.objects.exists()
        rebuilt = rebuild_open_periods()
        assert rebuilt >= 1
        assert HrPeriodDay.objects.filter(profile_id=profile.id).exists()

    def test_somebody_who_has_left_is_skipped(self, profile):
        HrEmploymentProfile.objects.filter(pk=profile.pk).update(is_active=False)
        assert rebuild_open_periods() == 0
        assert not HrPeriod.objects.exists()

    def test_a_closed_month_is_not_disturbed(self, profile):
        rebuild_open_periods()
        period = HrPeriod.objects.order_by("period_start").first()
        period.state = HrPeriod.State.LOCKED
        period.target_minutes = 1
        period.actual_minutes = 1
        period.balance_minutes = 0
        period.save()
        before = HrPeriodDay.objects.filter(period_id=period.id).count()
        rebuild_open_periods()
        period.refresh_from_db()
        assert period.state == HrPeriod.State.LOCKED
        assert HrPeriodDay.objects.filter(period_id=period.id).count() == before


class TestRecentMonths:
    def test_it_walks_backwards(self):
        assert list(_recent_months(date(2026, 3, 15), 3)) == [(2026, 3), (2026, 2), (2026, 1)]

    def test_it_crosses_the_year(self):
        assert list(_recent_months(date(2026, 1, 10), 3)) == [(2026, 1), (2025, 12), (2025, 11)]
