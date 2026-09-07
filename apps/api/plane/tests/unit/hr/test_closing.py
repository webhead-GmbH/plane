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


def an_hour_logged_on(profile, day):
    """An hour against a work item, which is the kind that can vanish underneath."""
    project = ProjectFactory(workspace=profile.workspace, created_by=profile.member)
    state = State.objects.filter(project=project).first() or State.objects.create(
        name="Todo", project=project, workspace=profile.workspace, group="unstarted"
    )
    issue = Issue.objects.create(project=project, workspace=profile.workspace, name="Something", state=state)
    moment = datetime(day.year, day.month, day.day, 9, 0, tzinfo=dt_timezone.utc)
    return IssueWorkLog.objects.create(
        workspace=profile.workspace,
        project=project,
        issue=issue,
        logged_by=profile.member,
        started_at=moment,
        logged_at=moment,
        duration=3600,
    )


def february(profile, worked=0):
    """The month before March, built, with something in it if asked for."""
    if worked:
        HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 2, 3),
            minutes=worked,
        )
    rebuild_period(profile, 2026, 2)
    return HrPeriod.objects.get(profile_id=profile.id, period_start=date(2026, 2, 1))


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
        issue = Issue.objects.create(project=project, workspace=profile.workspace, name="Ongoing", state=state)
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
        HrPeriodDay.objects.filter(period_id=period.id, work_date=date(2026, 3, 2)).update(needs_review=True)
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


class TestBalanceChainGaps:
    def test_a_reopened_month_in_the_chain_does_not_get_stepped_over(self, profile, approver):
        # January closes at +600. February closes at +600-x, then is reopened to be
        # corrected. March must not reach back past February to January, or
        # February's contribution vanishes from every month that follows.
        HrOpeningBalance.objects.create(
            workspace=profile.workspace,
            profile=profile,
            effective_on=date(2026, 1, 1),
            kind=HrOpeningBalance.Kind.TIME_BALANCE,
            minutes=600,
            basis="Opening",
        )
        for year, month in ((2026, 1), (2026, 2)):
            rebuild_period(profile, year, month)
            period = HrPeriod.objects.get(profile_id=profile.id, period_start=date(year, month, 1))
            submit(period, profile.member)
            approve(period, approver)
            lock(period, approver)

        january = HrPeriod.objects.get(profile_id=profile.id, period_start=date(2026, 1, 1))
        february = HrPeriod.objects.get(profile_id=profile.id, period_start=date(2026, 2, 1))
        reopen(february, approver, "A day was recorded against the wrong person.")

        rebuild_period(profile, *MARCH)
        march_period = HrPeriod.objects.get(profile_id=profile.id, period_start=date(2026, 3, 1))
        opening = opening_balance_for(march_period)
        assert opening != january.closing_balance_minutes
        # February is no longer closed, so March falls back to the agreed opening
        # rather than silently inheriting a figure from two months earlier.
        assert opening == 600

    def test_a_contiguous_chain_still_carries_forward(self, profile, approver):
        february = march(profile)  # any month; reuse the helper for a closed one
        submit(february, profile.member)
        approve(february, approver)
        closed = lock(february, approver)
        rebuild_period(profile, 2026, 4)
        april = HrPeriod.objects.get(profile_id=profile.id, period_start=date(2026, 4, 1))
        assert opening_balance_for(april) == closed.closing_balance_minutes


class TestRebuildGating:
    def test_a_submitted_month_is_not_rewritten_underneath_the_approver(self, profile):
        # Approving one set of figures and locking another is the failure this
        # prevents.
        period = submit(march(profile), profile.member)
        HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 3, 3),
            minutes=300,
        )
        assert rebuild_period(profile, *MARCH) is None
        day = HrPeriodDay.objects.get(period_id=period.id, work_date=date(2026, 3, 3))
        assert day.non_project_minutes == 0

    def test_an_approved_month_is_not_rewritten_either(self, profile, approver):
        through_to_approved(profile, approver)
        assert rebuild_period(profile, *MARCH) is None


class TestRelock:
    def test_closing_a_reopened_month_keeps_the_first_closing_on_the_record(self, profile, approver):
        period = lock(through_to_approved(profile, approver), approver)
        first_target = period.target_minutes
        reopen(period, approver, "Correcting a misfiled day.")

        period.refresh_from_db()
        submit(period, profile.member)
        approve(period, approver)
        relocked = lock(period, approver)

        superseded = relocked.snapshot["superseded"]
        assert len(superseded) == 1
        assert superseded[0]["target_minutes"] == first_target
        assert superseded[0]["reason"] == "Correcting a misfiled day."


class TestClosingCountsWhatIsThereAtTheTime:
    """The final rebuild, which for a long time did not happen.

    `lock` calls `rebuild_period`, and `rebuild_period` refuses anything that is
    not open or reopened — which an approved month is not. So the call returned
    immediately and the figures frozen were whatever had last been computed while
    the month was still open, missing everything recorded between the two.

    Nothing about it looked wrong: the month closed, the figures were plausible,
    and only somebody adding up the records by hand would ever have found the
    difference.
    """

    def test_hours_recorded_between_approval_and_closing_are_counted(self, profile, approver):
        period = through_to_approved(profile, approver)
        HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 3, 3),
            minutes=300,
        )

        closed = lock(period, approver)

        assert closed.actual_minutes == 300
        assert closed.non_project_minutes == 300

    def test_the_day_breakdown_is_rebuilt_too_not_only_the_total(self, profile, approver):
        period = through_to_approved(profile, approver)
        HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 3, 3),
            minutes=300,
        )

        lock(period, approver)

        day = HrPeriodDay.objects.get(period_id=period.id, work_date=date(2026, 3, 3))
        assert day.non_project_minutes == 300

    def test_the_snapshot_records_the_rebuilt_figures(self, profile, approver):
        """The snapshot is what an auditor reads, so it cannot describe the old total."""
        period = through_to_approved(profile, approver)
        HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 3, 3),
            minutes=300,
        )

        closed = lock(period, approver)

        assert closed.snapshot["totals"]["actual_minutes"] == 300

    def test_hours_that_vanished_before_closing_stop_it(self, profile, approver):
        """The rebuild now runs, so it can also flag — and that must not be swallowed.

        A worklog counted into the approved month and gone by the time it closes is
        the case the flag exists for. While the rebuild did nothing, the hours were
        simply dropped from the frozen total and nobody was asked about them.
        """
        worked = an_hour_logged_on(profile, date(2026, 3, 3))
        period = through_to_approved(profile, approver)
        worked.delete()

        with pytest.raises(TransitionRefused, match="marked for review"):
            lock(period, approver)


class TestTheMonthBeforeThisOne:
    """A running balance is a chain, and closing over a gap silently restarts it.

    `opening_balance_for` takes the previous month's closing figure only when that
    month is closed, and otherwise falls all the way back to the balance agreed
    when the module started counting. So closing March while February was still
    open did not carry February forward — it discarded every month since the
    beginning, and the loss then rode forward on every month after it.
    """

    def test_a_month_whose_predecessor_is_still_open_refuses_to_close(self, profile, approver):
        february(profile, worked=300)
        period = through_to_approved(profile, approver)

        with pytest.raises(TransitionRefused, match="February 2026"):
            lock(period, approver)

    def test_a_month_whose_predecessor_was_reopened_refuses_too(self, profile, approver):
        before = february(profile)
        submit(before, profile.member)
        approve(before, approver)
        lock(before, approver)
        reopen(before, approver, "A figure was queried.")

        period = through_to_approved(profile, approver)
        with pytest.raises(TransitionRefused, match="February 2026"):
            lock(period, approver)

    def test_an_empty_month_nobody_recorded_anything_in_is_not_a_gap(self, profile, approver):
        """One gets created merely by looking at it, and refusing on that is a wall."""
        rebuild_period(profile, 2026, 2)
        HrPeriodDay.objects.filter(period__period_start=date(2026, 2, 1)).update(target_minutes=0, actual_minutes=0)

        closed = lock(through_to_approved(profile, approver), approver)
        assert closed.state == HrPeriod.State.LOCKED

    def test_a_month_from_before_the_counting_began_is_not_a_gap_either(self, profile, approver):
        """Scrolling back through a year that predates the module creates rows.

        Those months carry a full target — the schedule reaches back as far as it
        is asked — but not one minute of it was ever owed, because the balance
        this person actually starts from was agreed on a later date. Treating them
        as a break in the chain makes the current month uncloseable on account of
        a shortfall that does not exist.
        """
        HrOpeningBalance.objects.create(
            workspace=profile.workspace,
            profile=profile,
            effective_on=date(2026, 3, 1),
            kind=HrOpeningBalance.Kind.TIME_BALANCE,
            minutes=0,
            basis="Agreed at the cut-over.",
        )
        # A month somebody merely looked at: a real target, nothing worked.
        february(profile)
        assert HrPeriodDay.objects.filter(period__period_start=date(2026, 2, 1), target_minutes__gt=0).exists()

        closed = lock(through_to_approved(profile, approver), approver)
        assert closed.state == HrPeriod.State.LOCKED

    def test_the_balance_is_carried_once_the_predecessor_is_closed(self, profile, approver):
        before = february(profile, worked=300)
        submit(before, profile.member)
        approve(before, approver)
        closed_before = lock(before, approver)

        closed = lock(through_to_approved(profile, approver), approver)

        assert closed.opening_balance_minutes == closed_before.closing_balance_minutes
        assert closed.opening_balance_minutes != 0


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
