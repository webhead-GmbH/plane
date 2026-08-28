# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Closing a month, and reopening one that turned out to be wrong."""

# Python imports
from datetime import date, datetime, timezone as dt_timezone
from uuid import uuid4

# Third-party imports
import pytest

# Module imports
from plane.db.models import Issue, IssueWorkLog, State
from plane.hr.models import (
    HrAbsence,
    HrAbsenceType,
    HrAuditLog,
    HrContract,
    HrEmploymentProfile,
    HrOpeningBalance,
    HrPeriod,
    HrPeriodDay,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.hr.services.closing import (
    TransitionRefused,
    approve,
    lock,
    opening_balance_for,
    reopen,
    submit,
)
from plane.hr.services.ledger import rebuild_period
from plane.tests.factories import ProjectFactory, UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

FULL = 462
MARCH = (2026, 3)
MARCH_WORKDAYS = 22


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
def approver():
    return new_user()


def march(profile):
    rebuild_period(profile, *MARCH)
    return HrPeriod.objects.get(profile_id=profile.id, period_start=date(2026, 3, 1))


def through_to_approved(profile, approver):
    period = march(profile)
    submit(period, profile.member)
    approve(period, approver)
    return period


class TestSubmit:
    def test_an_open_month_can_be_submitted(self, profile):
        period = submit(march(profile), profile.member)
        assert period.state == HrPeriod.State.SUBMITTED
        assert period.submitted_at is not None

    def test_a_running_timer_blocks_submission(self, profile):
        project = ProjectFactory(workspace=profile.workspace, created_by=profile.member)
        state = State.objects.filter(project=project).first() or State.objects.create(
            name="Todo", project=project, workspace=profile.workspace, group="unstarted"
        )
        issue = Issue.objects.create(
            project=project, workspace=profile.workspace, name="Ongoing", state=state
        )
        IssueWorkLog.objects.create(
            workspace=profile.workspace,
            project=project,
            issue=issue,
            logged_by=profile.member,
            started_at=datetime(2026, 3, 2, 8, 0, tzinfo=dt_timezone.utc),
            logged_at=datetime(2026, 3, 2, 8, 0, tzinfo=dt_timezone.utc),
            duration=None,
        )
        with pytest.raises(TransitionRefused, match="still running"):
            submit(march(profile), profile.member)

    def test_a_submitted_month_cannot_be_submitted_again(self, profile):
        period = submit(march(profile), profile.member)
        with pytest.raises(TransitionRefused):
            submit(period, profile.member)


class TestApprove:
    def test_a_submitted_month_can_be_approved(self, profile, approver):
        period = submit(march(profile), profile.member)
        approved = approve(period, approver)
        assert approved.state == HrPeriod.State.APPROVED
        assert approved.approved_by == approver

    def test_an_open_month_cannot_be_approved(self, profile, approver):
        with pytest.raises(TransitionRefused):
            approve(march(profile), approver)


class TestLock:
    def test_closing_freezes_the_figures(self, profile, approver):
        period = lock(through_to_approved(profile, approver), approver)
        assert period.state == HrPeriod.State.LOCKED
        assert period.target_minutes == FULL * MARCH_WORKDAYS
        assert period.actual_minutes == 0
        assert period.balance_minutes == -FULL * MARCH_WORKDAYS
        assert period.locked_at is not None

    def test_closing_records_what_the_figures_came_from(self, profile, approver):
        period = lock(through_to_approved(profile, approver), approver)
        snapshot = period.snapshot
        assert snapshot["timezone"] == "Europe/Vienna"
        assert snapshot["contract_id"] is not None
        assert snapshot["schedule_id"] is not None
        assert snapshot["records_target_hours"] is True
        # A target for every day of the month, so the figure stays explicable.
        assert len(snapshot["daily_target_minutes"]) == 31
        assert snapshot["daily_target_minutes"]["2026-03-02"] == FULL

    def test_a_closed_month_stops_being_rebuilt(self, profile, approver):
        period = lock(through_to_approved(profile, approver), approver)
        HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 3, 3),
            minutes=300,
        )
        assert rebuild_period(profile, *MARCH) is None
        period.refresh_from_db()
        assert period.actual_minutes == 0

    def test_records_that_fed_the_month_are_stamped(self, profile, approver):
        entry = HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 3, 3),
            minutes=300,
        )
        period = lock(through_to_approved(profile, approver), approver)
        entry.refresh_from_db()
        assert entry.locked_period_id == period.id

    def test_a_month_with_days_marked_for_review_refuses_to_close(self, profile, approver):
        period = through_to_approved(profile, approver)
        HrPeriodDay.objects.filter(period_id=period.id, work_date=date(2026, 3, 2)).update(
            needs_review=True
        )
        with pytest.raises(TransitionRefused, match="marked for review"):
            lock(period, approver)

    def test_an_unapproved_month_cannot_be_closed(self, profile, approver):
        with pytest.raises(TransitionRefused):
            lock(march(profile), approver)

    def test_closing_is_written_down(self, profile, approver):
        period = lock(through_to_approved(profile, approver), approver)
        entry = HrAuditLog.objects.get(object_id=period.id, action="period_locked")
        assert entry.changes["target_minutes"] == FULL * MARCH_WORKDAYS
        assert entry.actor == approver


class TestBalanceCarry:
    def test_the_first_month_starts_from_the_agreed_opening_balance(self, profile, approver):
        HrOpeningBalance.objects.create(
            workspace=profile.workspace,
            profile=profile,
            effective_on=date(2026, 1, 1),
            kind=HrOpeningBalance.Kind.TIME_BALANCE,
            minutes=600,
            confidence=HrOpeningBalance.Confidence.AGREED,
            basis="Agreed with the employee at cut-over.",
        )
        period = lock(through_to_approved(profile, approver), approver)
        assert period.opening_balance_minutes == 600
        assert period.closing_balance_minutes == 600 - FULL * MARCH_WORKDAYS

    def test_a_later_month_starts_where_the_previous_closed_month_ended(self, profile, approver):
        march_period = lock(through_to_approved(profile, approver), approver)
        rebuild_period(profile, 2026, 4)
        april = HrPeriod.objects.get(profile_id=profile.id, period_start=date(2026, 4, 1))
        assert opening_balance_for(april) == march_period.closing_balance_minutes

    def test_time_taken_off_in_lieu_comes_off_the_running_balance(self, profile, approver):
        lieu = HrAbsenceType.objects.create(
            workspace=profile.workspace,
            code="lieu",
            name_de="Zeitausgleich",
            credits_actual=True,
            consumes_balance=True,
        )
        HrAbsence.objects.create(
            workspace=profile.workspace,
            profile=profile,
            absence_type=lieu,
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
            state=HrAbsence.State.APPROVED,
        )
        HrOpeningBalance.objects.create(
            workspace=profile.workspace,
            profile=profile,
            effective_on=date(2026, 1, 1),
            kind=HrOpeningBalance.Kind.TIME_BALANCE,
            minutes=10000,
            basis="Opening",
        )
        period = lock(through_to_approved(profile, approver), approver)
        # The day itself came out level, so the hours must leave the balance
        # explicitly or they would be both credited and kept.
        day = HrPeriodDay.objects.get(period_id=period.id, work_date=date(2026, 3, 2))
        assert day.balance_minutes == 0
        assert day.balance_consumed_minutes == FULL
        assert period.closing_balance_minutes == 10000 + period.balance_minutes - FULL


class TestReopen:
    def test_reopening_needs_a_reason(self, profile, approver):
        period = lock(through_to_approved(profile, approver), approver)
        with pytest.raises(TransitionRefused, match="why"):
            reopen(period, approver, "")

    def test_reopening_keeps_the_figures_it_was_closed_on(self, profile, approver):
        period = lock(through_to_approved(profile, approver), approver)
        original_target = period.target_minutes
        reopened = reopen(period, approver, "A day was entered against the wrong person.")
        assert reopened.state == HrPeriod.State.REOPENED
        superseded = reopened.snapshot["superseded"]
        assert len(superseded) == 1
        assert superseded[0]["target_minutes"] == original_target
        assert superseded[0]["reason"] == "A day was entered against the wrong person."

    def test_reopening_lets_the_records_be_edited_again(self, profile, approver):
        entry = HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 3, 3),
            minutes=300,
        )
        period = lock(through_to_approved(profile, approver), approver)
        reopen(period, approver, "Correcting an entry.")
        entry.refresh_from_db()
        assert entry.locked_period_id is None

    def test_a_reopened_month_is_rebuilt_again(self, profile, approver):
        period = lock(through_to_approved(profile, approver), approver)
        reopen(period, approver, "Correcting an entry.")
        HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 3, 3),
            minutes=300,
        )
        assert rebuild_period(profile, *MARCH) is not None
        day = HrPeriodDay.objects.get(period_id=period.id, work_date=date(2026, 3, 3))
        assert day.non_project_minutes == 300

    def test_an_open_month_cannot_be_reopened(self, profile):
        with pytest.raises(TransitionRefused):
            reopen(march(profile), profile.member, "No reason to.")
