# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rebuilding a month from the records behind it."""

# Python imports
from datetime import date, datetime, timezone as dt_timezone

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
    HrHoliday,
    HrHolidayCalendar,
    HrPeriod,
    HrPeriodDay,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.hr.services.refusal import Refused
from plane.hr.services.ledger import (
    has_running_timer,
    period_totals,
    rebuild_period,
    settle_day,
)
from plane.tests.factories import ProjectFactory, UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

VIENNA = "Europe/Vienna"
FULL = 462  # 7:42 — a day of a 38.5 hour week over five days


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=dt_timezone.utc)


@pytest.fixture
def workspace_and_user():
    user = UserFactory()
    workspace = WorkspaceFactory(owner=user)
    WorkspaceMemberFactory(workspace=workspace, member=user)
    return workspace, user


@pytest.fixture
def profile(workspace_and_user):
    workspace, user = workspace_and_user
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone=VIENNA,
        hire_date=date(2020, 1, 1),
    )
    HrContract.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2020, 1, 1),
        arrangement=HrContract.Arrangement.ONSITE_FULL_TIME,
        records_target_hours=True,
        weekly_minutes=2310,
    )
    HrWorkSchedule.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2020, 1, 1),
        monday_minutes=FULL,
        tuesday_minutes=FULL,
        wednesday_minutes=FULL,
        thursday_minutes=FULL,
        friday_minutes=FULL,
    )
    return profile


@pytest.fixture
def project(workspace_and_user):
    workspace, user = workspace_and_user
    return ProjectFactory(workspace=workspace, created_by=user, updated_by=user)


@pytest.fixture
def issue(project, workspace_and_user):
    workspace, user = workspace_and_user
    state = State.objects.filter(project=project).first() or State.objects.create(
        name="Todo", project=project, workspace=workspace, group="unstarted"
    )
    return Issue.objects.create(project=project, workspace=workspace, name="A work item", state=state, created_by=user)


def log_hours(profile, issue, when, seconds):
    return IssueWorkLog.objects.create(
        workspace_id=profile.workspace_id,
        project_id=issue.project_id,
        issue=issue,
        logged_by_id=profile.member_id,
        started_at=when,
        logged_at=when,
        duration=seconds,
    )


class TestRebuild:
    def test_a_month_with_no_records_still_produces_every_day(self, profile):
        rebuild_period(profile, 2026, 3)
        days = HrPeriodDay.objects.filter(profile_id=profile.id)
        assert days.count() == 31

    def test_working_days_carry_a_target_and_weekends_do_not(self, profile):
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        saturday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 7))
        assert monday.target_minutes == FULL
        assert saturday.target_minutes == 0

    def test_logged_hours_land_on_the_day_they_were_worked(self, profile, issue):
        log_hours(profile, issue, utc(2026, 3, 2, 8, 0), FULL * 60)
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.project_minutes == FULL
        assert monday.balance_minutes == 0

    def test_hours_just_after_local_midnight_belong_to_the_next_day(self, profile, issue):
        # 23:30 UTC on the 2nd is 00:30 on the 3rd in Vienna. Reading this in UTC
        # would file it against the wrong day, and at a month end, the wrong month.
        log_hours(profile, issue, utc(2026, 3, 2, 23, 30), 3600)
        rebuild_period(profile, 2026, 3)
        second = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        third = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 3))
        assert second.project_minutes == 0
        assert third.project_minutes == 60

    def test_non_project_time_is_counted_too(self, profile):
        HrTimeEntry.objects.create(
            workspace_id=profile.workspace_id,
            profile=profile,
            entry_date=date(2026, 3, 2),
            minutes=120,
            category=HrTimeEntry.Category.MEETING,
        )
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.non_project_minutes == 120
        assert monday.actual_minutes == 120

    def test_rounding_is_applied_once_per_day_not_per_entry(self, profile, issue):
        # Ten entries of 59 seconds. Rounded individually they would vanish.
        for _ in range(10):
            log_hours(profile, issue, utc(2026, 3, 2, 9, 0), 59)
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.project_minutes == 10

    def test_a_running_timer_is_not_counted(self, profile, issue):
        IssueWorkLog.objects.create(
            workspace_id=profile.workspace_id,
            project_id=issue.project_id,
            issue=issue,
            logged_by_id=profile.member_id,
            started_at=utc(2026, 3, 2, 8, 0),
            logged_at=utc(2026, 3, 2, 8, 0),
            duration=None,
        )
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.project_minutes == 0

    def test_rebuilding_twice_changes_nothing(self, profile, issue):
        log_hours(profile, issue, utc(2026, 3, 2, 8, 0), 3600)
        rebuild_period(profile, 2026, 3)
        first = period_totals(HrPeriod.objects.get(profile_id=profile.id))
        rebuild_period(profile, 2026, 3)
        second = period_totals(HrPeriod.objects.get(profile_id=profile.id))
        assert first == second
        assert HrPeriodDay.objects.filter(profile_id=profile.id).count() == 31

    def test_no_target_is_recorded_when_the_contract_says_not_to(self, profile):
        # For someone invoicing their own hours, recording a daily obligation is a
        # decision in its own right and the default is not to.
        HrContract.objects.filter(profile_id=profile.id).update(records_target_hours=False)
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.target_minutes == 0
        assert monday.balance_minutes == 0


class TestDisappearingHours:
    def test_hours_removed_after_being_counted_are_flagged_not_silently_dropped(self, profile, issue):
        worklog = log_hours(profile, issue, utc(2026, 3, 2, 8, 0), 3600)
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.project_minutes == 60
        assert monday.needs_review is False

        # Deleting a work item takes every timer on it, including other people's.
        worklog.delete()
        rebuild_period(profile, 2026, 3)

        monday.refresh_from_db()
        assert monday.project_minutes == 0
        assert monday.needs_review is True

        entry = HrAuditLog.objects.get(profile_id=profile.id, action="counted_hours_disappeared")
        assert entry.changes["date"] == "2026-03-02"
        assert str(worklog.id) in entry.changes["missing_worklog_ids"]

    def test_a_day_that_never_had_hours_is_not_flagged(self, profile):
        rebuild_period(profile, 2026, 3)
        rebuild_period(profile, 2026, 3)
        assert not HrPeriodDay.objects.filter(profile_id=profile.id, needs_review=True).exists()
        assert not HrAuditLog.objects.filter(action="counted_hours_disappeared").exists()


class TestHoursAcrossWorkspaces:
    """One company, several workspaces, one set of hours.

    Somebody employed here is employed once. Counting only the workspace their
    paperwork happens to live in would split their month in half and invent a
    shortfall against them for hours they actually worked.
    """

    def test_hours_from_another_workspace_count_towards_the_same_month(self, profile, issue):
        # Four hours in the workspace that administers their HR.
        log_hours(profile, issue, utc(2026, 3, 2, 8, 0), 4 * 3600)

        # Three more in a second workspace of the same company.
        other = WorkspaceFactory(owner=profile.member)
        WorkspaceMemberFactory(workspace=other, member=profile.member)
        other_project = ProjectFactory(workspace=other, created_by=profile.member)
        state = State.objects.filter(project=other_project).first() or State.objects.create(
            name="Todo", project=other_project, workspace=other, group="unstarted"
        )
        other_issue = Issue.objects.create(project=other_project, workspace=other, name="Elsewhere", state=state)
        IssueWorkLog.objects.create(
            workspace=other,
            project=other_project,
            issue=other_issue,
            logged_by=profile.member,
            started_at=utc(2026, 3, 2, 13, 0),
            logged_at=utc(2026, 3, 2, 13, 0),
            duration=3 * 3600,
        )

        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.project_minutes == 7 * 60
        # Seven hours worked against 7:42 owed, not four against 7:42.
        assert monday.balance_minutes == 420 - FULL

    def test_one_person_gets_one_employment_record(self, profile):
        from django.db.utils import IntegrityError

        other = WorkspaceFactory(owner=profile.member)
        WorkspaceMemberFactory(workspace=other, member=profile.member)
        with pytest.raises(IntegrityError):
            HrEmploymentProfile.objects.create(workspace=other, member=profile.member, hire_date=date(2024, 1, 1))

    def test_a_timer_running_in_another_workspace_still_counts_as_running(self, profile):
        other = WorkspaceFactory(owner=profile.member)
        WorkspaceMemberFactory(workspace=other, member=profile.member)
        other_project = ProjectFactory(workspace=other, created_by=profile.member)
        state = State.objects.filter(project=other_project).first() or State.objects.create(
            name="Todo", project=other_project, workspace=other, group="unstarted"
        )
        other_issue = Issue.objects.create(project=other_project, workspace=other, name="Elsewhere", state=state)
        IssueWorkLog.objects.create(
            workspace=other,
            project=other_project,
            issue=other_issue,
            logged_by=profile.member,
            started_at=utc(2026, 3, 2, 8, 0),
            logged_at=utc(2026, 3, 2, 8, 0),
            duration=None,
        )
        assert has_running_timer(profile, 2026, 3) is True


class TestRecordingSwitches:
    def test_a_person_with_no_leave_account_cannot_spend_leave(self, profile):
        # Somebody invoicing their own hours has no leave to draw on, so an
        # absence that would spend some credits nothing for them.
        HrContract.objects.filter(profile_id=profile.id).update(records_target_hours=False, records_leave_account=False)
        leave = HrAbsenceType.objects.create(
            workspace=profile.workspace,
            code="urlaub",
            name_de="Urlaub",
            credits_actual=True,
            consumes_leave_entitlement=True,
        )
        HrAbsence.objects.create(
            workspace=profile.workspace,
            profile=profile,
            absence_type=leave,
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
            state=HrAbsence.State.APPROVED,
        )
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.absence_minutes == 0
        assert monday.leave_minutes == 0

    def test_a_leave_account_survives_having_no_daily_target(self, profile):
        # The two switches are independent: no obligation to work a set day does
        # not mean no leave account.
        HrContract.objects.filter(profile_id=profile.id).update(records_target_hours=False, records_leave_account=True)
        leave = HrAbsenceType.objects.create(
            workspace=profile.workspace,
            code="urlaub",
            name_de="Urlaub",
            credits_actual=True,
            consumes_leave_entitlement=True,
        )
        HrAbsence.objects.create(
            workspace=profile.workspace,
            profile=profile,
            absence_type=leave,
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
            state=HrAbsence.State.APPROVED,
        )
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.target_minutes == 0
        assert monday.leave_minutes == FULL

    def test_no_holiday_pay_without_a_recorded_working_obligation(self, profile):
        HrContract.objects.filter(profile_id=profile.id).update(records_target_hours=False)
        calendar = HrHolidayCalendar.objects.create(
            workspace=profile.workspace, name="AT", country_code="AT", is_default=True
        )
        HrHoliday.objects.create(
            workspace=profile.workspace,
            calendar=calendar,
            date=date(2026, 3, 2),
            name_de="Testfeiertag",
        )
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        assert monday.holiday_minutes == 0


class TestReviewFlag:
    def test_a_flag_survives_later_rebuilds_until_somebody_settles_it(self, profile, issue):
        worklog = log_hours(profile, issue, utc(2026, 3, 2, 8, 0), 3600)
        rebuild_period(profile, 2026, 3)
        worklog.delete()
        rebuild_period(profile, 2026, 3)
        rebuild_period(profile, 2026, 3)

        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        # Clearing it on the next pass would make the discrepancy come and go
        # before anybody had a chance to look at it.
        assert monday.needs_review is True

        settle_day(monday, profile.member, "Duplicate entry, removed on purpose.")
        monday.refresh_from_db()
        assert monday.needs_review is False
        assert HrAuditLog.objects.filter(action="review_settled").exists()

    def test_settling_requires_saying_what_was_decided(self, profile):
        rebuild_period(profile, 2026, 3)
        monday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 2))
        with pytest.raises(Refused):
            settle_day(monday, profile.member, "   ")

    def test_moving_an_entry_within_the_month_is_not_a_loss(self, profile, issue):
        # A correction, not a disappearance. Comparing day by day would report the
        # day it left as having lost hours the month never lost.
        worklog = log_hours(profile, issue, utc(2026, 3, 2, 8, 0), 3600)
        rebuild_period(profile, 2026, 3)
        worklog.started_at = utc(2026, 3, 4, 8, 0)
        worklog.logged_at = utc(2026, 3, 4, 8, 0)
        worklog.save()
        rebuild_period(profile, 2026, 3)

        assert not HrPeriodDay.objects.filter(profile_id=profile.id, needs_review=True).exists()
        assert not HrAuditLog.objects.filter(action="counted_hours_disappeared").exists()
        assert HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 4)).project_minutes == 60


class TestClosedMonths:
    def test_a_closed_month_is_left_alone(self, profile, issue):
        log_hours(profile, issue, utc(2026, 3, 2, 8, 0), 3600)
        rebuild_period(profile, 2026, 3)
        period = HrPeriod.objects.get(profile_id=profile.id)
        period.state = HrPeriod.State.LOCKED
        period.target_minutes = 100
        period.actual_minutes = 60
        period.balance_minutes = -40
        period.save()

        # More hours arrive for a month that has already been closed.
        log_hours(profile, issue, utc(2026, 3, 3, 8, 0), 7200)
        assert rebuild_period(profile, 2026, 3) is None

        tuesday = HrPeriodDay.objects.get(profile_id=profile.id, work_date=date(2026, 3, 3))
        assert tuesday.project_minutes == 0

    def test_the_database_refuses_to_close_a_month_without_figures(self, profile):
        from django.db.utils import IntegrityError

        rebuild_period(profile, 2026, 3)
        period = HrPeriod.objects.get(profile_id=profile.id)
        period.state = HrPeriod.State.LOCKED
        with pytest.raises(IntegrityError):
            period.save()
