# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Where a month's hours went, and the ways a detail screen disagrees with them.

A detail that does not add up to the total it sits under is worse than no
detail: it turns one number somebody trusted into two numbers nobody can. So
almost every case here is the same assertion in a different disguise — the rows
reconcile to the figure the month already reports.

The three ways that goes wrong are all invisible from the outside. Rounding is
applied once per person, per day, per project, so summing per-row minutes drifts
upward. The day an hour lands on is decided in the *subject's* zone, so a
`__date` lookup answers differently for a manager than for the person. And hours
are counted wherever they were logged, so any workspace filter quietly shows
less than the total it explains.
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
    HrContract,
    HrEmploymentProfile,
    HrPeriod,
    HrPeriodDay,
    HrTimeEntry,
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
VIENNA = "Europe/Vienna"
URL = "/api/hr/worklogs/"


def new_user():
    return UserFactory(username=uuid4().hex)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def employ(workspace, user, is_hr_manager=False):
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.ADMIN.value)
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone=VIENNA,
        hire_date=date(2024, 1, 1),
        is_hr_manager=is_hr_manager,
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
def person():
    user = new_user()
    workspace = WorkspaceFactory(owner=user)
    return user, employ(workspace, user, is_hr_manager=True)


def somewhere_to_work(user, workspace, name="Something"):
    # A distinct project per call: ProjectFactory does get_or_create on
    # (name, workspace), so reusing the default name hands back the same project
    # and the second membership collides on its unique constraint.
    project = ProjectFactory(
        workspace=workspace,
        created_by=user,
        name=f"{name} project",
        # The factory leaves the identifier blank, and a workspace may hold only
        # one blank one. It is also what a detail row shows as the work item's
        # key, so a test without it would not be exercising the column.
        identifier=uuid4().hex[:6].upper(),
    )
    ProjectMemberFactory(project=project, member=user, role=ROLE.ADMIN.value)
    state = State.objects.create(workspace=workspace, project=project, name="Doing", group="started")
    issue = Issue.objects.create(workspace=workspace, project=project, name=name, state=state)
    return project, issue


def log(profile, issue, when, seconds):
    return IssueWorkLog.objects.create(
        workspace_id=issue.workspace_id,
        project_id=issue.project_id,
        issue=issue,
        logged_by_id=profile.member_id,
        started_at=when,
        logged_at=when,
        duration=seconds,
    )


def utc_at(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=utc.utc)


def ask(user, profile, group_by="day", year=2026, month=3):
    return client_for(user).get(f"{URL}?profile_id={profile.id}&year={year}&month={month}&group_by={group_by}")


def close(profile):
    """Freeze the month. The figures are supplied because the database refuses a
    closed month without the ones it was closed on."""
    HrPeriod.objects.filter(profile_id=profile.id).update(
        state=HrPeriod.State.LOCKED,
        target_minutes=9240,
        actual_minutes=month_minutes(profile),
        balance_minutes=0,
    )


def month_minutes(profile):
    """What the month itself says the work-item hours came to."""
    return sum(
        HrPeriodDay.objects.filter(profile_id=profile.id, work_date__month=3, work_date__year=2026).values_list(
            "project_minutes", flat=True
        )
    )


class TestTheRowsAddUpToTheMonth:
    def test_the_total_is_the_month_s_own_figure(self, person):
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        log(profile, issue, utc_at(2026, 3, 2, 8), 3600)
        log(profile, issue, utc_at(2026, 3, 3, 9), 1800)
        rebuild_period(profile, *MARCH)

        body = ask(user, profile).json()

        assert body["work_item_minutes"] == month_minutes(profile)
        assert body["work_item_minutes"] == 90

    def test_short_entries_do_not_drift_upward(self, person):
        """Four 40-second entries are four minutes rounded singly and three here.

        The ledger rounds once on the summed seconds of a day and project. The
        numbers matter: each entry rounds UP on its own and the four of them
        round DOWN together, so this fails if the rounding ever moves to the row.
        Ten 59-second entries would not — they come to ten either way, which is
        why the first version of this test could not have caught the drift it
        was written to catch.
        """
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        for index in range(4):
            log(profile, issue, utc_at(2026, 3, 2, 8, index), 40)
        rebuild_period(profile, *MARCH)

        body = ask(user, profile).json()

        # 160 seconds together: (160 + 30) // 60 = 3. Singly: 1 + 1 + 1 + 1 = 4.
        assert body["work_item_minutes"] == month_minutes(profile)
        assert body["work_item_minutes"] == 3
        # And the rows themselves carry raw seconds, so nothing downstream can
        # round them one at a time.
        rows = body["groups"][0]["rows"]
        assert [row["seconds"] for row in rows] == [40] * 4

    def test_grouping_by_day_or_project_still_adds_up(self, person):
        user, profile = person
        _, first = somewhere_to_work(user, profile.workspace, name="One")
        second_project, second = somewhere_to_work(user, profile.workspace, name="Two")
        assert second_project is not None
        log(profile, first, utc_at(2026, 3, 2, 8), 59)
        log(profile, first, utc_at(2026, 3, 2, 9), 59)
        log(profile, second, utc_at(2026, 3, 3, 8), 1800)
        rebuild_period(profile, *MARCH)

        for grouping in ("day", "project"):
            body = ask(user, profile, grouping).json()
            assert body["totals_reconcile"] is True
            assert sum(group["minutes"] for group in body["groups"]) == body["work_item_minutes"]
            assert body["work_item_minutes"] == month_minutes(profile)

    def test_a_grouping_that_splits_a_rounding_bucket_says_so(self, person):
        """By work item the subtotals need not close, and the screen is told."""
        user, profile = person
        body = ask(user, profile, "work_item").json()
        assert body["totals_reconcile"] is False


class TestTheDayIsTheSubjectsDay:
    def test_a_late_evening_hour_lands_on_the_next_day_in_vienna(self, person):
        """23:30 UTC on the 2nd is 00:30 on the 3rd where this person works.

        A `__date` lookup would answer with the *reader's* zone, so a manager in
        another country would see the same hour on a different day from the
        person whose month it is — and from the month's own day row.
        """
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        log(profile, issue, utc_at(2026, 3, 2, 23, 30), 3600)
        rebuild_period(profile, *MARCH)

        body = ask(user, profile).json()

        assert [row["day"] for group in body["groups"] for row in group["rows"]] == ["2026-03-03"]

    def test_an_hour_at_the_month_boundary_belongs_to_one_month_only(self, person):
        """23:30 UTC on 31 March is already April in Vienna."""
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        log(profile, issue, utc_at(2026, 3, 31, 23, 30), 3600)

        march = ask(user, profile, year=2026, month=3).json()
        april = ask(user, profile, year=2026, month=4).json()

        assert march["work_item_minutes"] == 0
        assert april["work_item_minutes"] == 60

    def test_an_entry_with_no_start_time_falls_on_the_day_it_was_worked(self, person):
        """A backdated entry sorts and groups by when it counts, not when it was typed."""
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        entry = log(profile, issue, utc_at(2026, 3, 4, 10), 3600)
        entry.started_at = None
        entry.logged_at = utc_at(2026, 3, 4, 10)
        entry.save(update_fields=["started_at", "logged_at"])
        rebuild_period(profile, *MARCH)

        row = ask(user, profile).json()["groups"][0]["rows"][0]

        assert row["day"] == "2026-03-04"
        assert row["entered_by_hand"] is True


class TestEveryWorkspaceCounts:
    def test_hours_logged_elsewhere_are_in_the_same_month(self, person):
        """The ledger has no workspace filter on purpose; nor may the detail.

        Filtering by workspace — or by the projects the reader belongs to — makes
        the rows come to less than the figure above them, with nothing on screen
        to say why.
        """
        user, profile = person
        _, here = somewhere_to_work(user, profile.workspace, name="Here")

        elsewhere = WorkspaceFactory(owner=user)
        WorkspaceMemberFactory(workspace=elsewhere, member=user, role=ROLE.ADMIN.value)
        _, there = somewhere_to_work(user, elsewhere, name="There")

        log(profile, here, utc_at(2026, 3, 2, 8), 3600)
        log(profile, there, utc_at(2026, 3, 3, 8), 3600)
        rebuild_period(profile, *MARCH)

        body = ask(user, profile, "workspace").json()

        assert body["work_item_minutes"] == month_minutes(profile)
        assert body["work_item_minutes"] == 120
        assert len(body["groups"]) == 2


class TestWhatIsNotAnHourYet:
    def test_a_running_timer_is_shown_and_counts_nothing(self, person):
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        log(profile, issue, utc_at(2026, 3, 2, 8), 3600)
        running = log(profile, issue, utc_at(2026, 3, 2, 14), None)
        running.duration = None
        running.save(update_fields=["duration"])
        rebuild_period(profile, *MARCH)

        body = ask(user, profile).json()

        assert body["running"] == 1
        assert body["work_item_minutes"] == month_minutes(profile)
        assert body["work_item_minutes"] == 60
        assert any(row["is_running"] for group in body["groups"] for row in group["rows"])

    def test_non_project_hours_are_their_own_lane(self, person):
        """They have no work item, so mixing them in would name a figure nothing."""
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        log(profile, issue, utc_at(2026, 3, 2, 8), 3600)
        HrTimeEntry.objects.create(
            workspace=profile.workspace, profile=profile, entry_date=date(2026, 3, 2), minutes=90
        )
        rebuild_period(profile, *MARCH)

        body = ask(user, profile).json()

        assert body["work_item_minutes"] == 60
        assert body["other_minutes"] == 90
        assert len(body["other"]) == 1


class TestASettledMonthShowsWhatItCounted:
    def test_hours_added_after_closing_are_not_in_the_detail(self, person):
        """The figures stopped moving, so the rows explaining them must too."""
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        log(profile, issue, utc_at(2026, 3, 2, 8), 3600)
        rebuild_period(profile, *MARCH)
        close(profile)

        log(profile, issue, utc_at(2026, 3, 3, 8), 3600)
        body = ask(user, profile).json()

        assert body["is_settled"] is True
        assert body["work_item_minutes"] == 60

    def test_an_entry_the_month_counted_and_lost_is_named(self, person):
        """Deleting a work item takes its hours with it. The month still counted them."""
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        entry = log(profile, issue, utc_at(2026, 3, 2, 8), 3600)
        rebuild_period(profile, *MARCH)
        close(profile)
        entry.delete()

        body = ask(user, profile).json()

        # Soft-deleted, so it still comes back and can say it is gone.
        assert body["withdrawn"] == 1
        assert any(row["gone"] for group in body["groups"] for row in group["rows"])

    def test_moving_the_person_afterwards_does_not_move_the_frozen_rows(self, person):
        """A closed month is explained by the day it filed each entry under.

        The zone that decided those days is editable and is not guarded against
        a settled month, so deriving the day again today can move rows between
        days, re-form the rounding buckets, and drop anything that had crossed
        the month boundary — reporting an entry that is sitting there untouched
        as one that has gone missing.
        """
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        # 23:30 UTC on 28 February is 00:30 on 1 March in Vienna, so the month
        # counts it. Read back as UTC it would fall outside March entirely.
        log(profile, issue, utc_at(2026, 2, 28, 23, 30), 3600)
        rebuild_period(profile, *MARCH)
        frozen = month_minutes(profile)
        assert frozen == 60
        close(profile)

        profile.timezone = "UTC"
        profile.save(update_fields=["timezone"])

        body = ask(user, profile).json()

        assert body["work_item_minutes"] == frozen
        assert body["missing"] == 0
        assert [row["day"] for group in body["groups"] for row in group["rows"]] == ["2026-03-01"]

    def test_an_entry_erased_outright_is_counted_as_missing(self, person):
        """Only the identifier was ever kept, so there is nothing left to render."""
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        entry = log(profile, issue, utc_at(2026, 3, 2, 8), 3600)
        rebuild_period(profile, *MARCH)
        close(profile)
        IssueWorkLog.all_objects.filter(pk=entry.id).delete()

        body = ask(user, profile).json()

        assert body["missing"] == 1


class TestReadingDoesNotChangeAnything:
    def test_a_get_does_not_rebuild_the_month(self, person):
        """A screen that recomputed on being looked at would rewrite read figures."""
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        log(profile, issue, utc_at(2026, 3, 2, 8), 3600)
        rebuild_period(profile, *MARCH)
        before = list(
            HrPeriodDay.objects.filter(profile_id=profile.id)
            .order_by("work_date")
            .values_list("last_rebuilt_at", flat=True)
        )

        ask(user, profile)

        after = list(
            HrPeriodDay.objects.filter(profile_id=profile.id)
            .order_by("work_date")
            .values_list("last_rebuilt_at", flat=True)
        )
        assert before == after


class TestWhoMayRead:
    def test_a_colleague_is_not_found(self, person):
        user, profile = person
        colleague = new_user()
        theirs = employ(profile.workspace, colleague)

        assert client_for(colleague).get(f"{URL}?profile_id={profile.id}").status_code == 404
        # And their own is fine.
        assert client_for(colleague).get(f"{URL}?profile_id={theirs.id}").status_code == 200

    def test_a_manager_may_read_anyone(self, person):
        user, profile = person
        colleague = new_user()
        theirs = employ(profile.workspace, colleague)

        assert client_for(user).get(f"{URL}?profile_id={theirs.id}").status_code == 200

    def test_somebody_with_no_employment_record_is_refused(self, person):
        _, profile = person
        outsider = new_user()
        WorkspaceMemberFactory(workspace=profile.workspace, member=outsider, role=ROLE.MEMBER.value)

        assert client_for(outsider).get(f"{URL}?profile_id={profile.id}").status_code in (403, 404)

    def test_no_profile_id_means_your_own(self, person):
        user, profile = person
        assert client_for(user).get(URL).status_code == 200


class TestBadParametersDoNotBreakIt:
    @pytest.mark.parametrize(
        "query",
        ["month=13", "month=0", "month=-1", "year=0", "year=99999999", "month=abc", "year=", "group_by=nonsense"],
    )
    def test_a_typo_still_answers(self, person, query):
        user, profile = person
        response = client_for(user).get(f"{URL}?profile_id={profile.id}&{query}")
        assert response.status_code == 200

    def test_an_unknown_grouping_falls_back_rather_than_reaching_the_query(self, person):
        user, profile = person
        assert ask(user, profile, "'; drop table --").json()["grouping"] == "day"

    def test_a_profile_id_that_is_not_a_uuid_does_not_500(self, person):
        user, _ = person
        assert client_for(user).get(f"{URL}?profile_id=not-a-uuid").status_code in (400, 404)


class TestWhatTheRowsSay:
    def test_a_row_names_its_work_item_and_project(self, person):
        user, profile = person
        project, issue = somewhere_to_work(user, profile.workspace, name="Fix the thing")
        log(profile, issue, utc_at(2026, 3, 2, 8), 3600)

        row = ask(user, profile).json()["groups"][0]["rows"][0]

        assert row["issue_name"] == "Fix the thing"
        assert row["issue_sequence_id"] == issue.sequence_id
        assert row["project_identifier"] == project.identifier
        assert row["project_name"] == project.name

    def test_a_timer_the_sweeper_closed_says_it_was_not_measured(self, person):
        """The duration beside it is a ceiling, not a measurement."""
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        entry = log(profile, issue, utc_at(2026, 3, 2, 8), 3600)
        entry.description = "[automatically stopped] whatever it was"
        entry.save(update_fields=["description"])

        row = ask(user, profile).json()["groups"][0]["rows"][0]

        assert row["auto_stopped"] is True

    def test_rows_come_back_newest_first(self, person):
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        for day in (2, 4, 3):
            log(profile, issue, utc_at(2026, 3, day, 8), 3600)

        days = [row["day"] for group in ask(user, profile, "project").json()["groups"] for row in group["rows"]]

        assert days == sorted(days, reverse=True)


class TestGroupingShapes:
    def test_a_week_group_is_named_by_the_monday_it_starts_on(self, person):
        """The Monday, not the first day that happens to hold hours.

        A header reading "week of" a Thursday names the wrong seven days, and
        two adjacent weeks then carry labels that are not a week apart.
        """
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        # Nothing on Monday 2 or Tuesday 3 March; the week still began on the 2nd.
        log(profile, issue, utc_at(2026, 3, 4, 8), 3600)
        log(profile, issue, utc_at(2026, 3, 5, 8), 3600)
        log(profile, issue, utc_at(2026, 3, 9, 8), 3600)

        groups = ask(user, profile, "week").json()["groups"]

        assert len(groups) == 2
        assert [group["first_day"] for group in groups] == ["2026-03-09", "2026-03-02"]
        assert {group["entries"] for group in groups} == {1, 2}

    def test_week_and_workspace_subtotals_are_not_warned_about(self, person):
        """Neither can split a (day, project) bucket, so their sums always close.

        A week is a whole number of days and a project belongs to one workspace.
        Warning about arithmetic that closes to the minute teaches somebody to
        distrust a figure that is right.
        """
        user, profile = person
        _, issue = somewhere_to_work(user, profile.workspace)
        log(profile, issue, utc_at(2026, 3, 2, 8), 40)
        log(profile, issue, utc_at(2026, 3, 2, 9), 40)
        log(profile, issue, utc_at(2026, 3, 3, 8), 1800)
        rebuild_period(profile, *MARCH)

        for grouping in ("week", "workspace"):
            body = ask(user, profile, grouping).json()
            assert body["totals_reconcile"] is True
            assert sum(group["minutes"] for group in body["groups"]) == body["work_item_minutes"]
            assert body["work_item_minutes"] == month_minutes(profile)

    def test_work_item_groups_are_biggest_first(self, person):
        user, profile = person
        _, small = somewhere_to_work(user, profile.workspace, name="Small")
        _, large = somewhere_to_work(user, profile.workspace, name="Large")
        log(profile, small, utc_at(2026, 3, 2, 8), 600)
        log(profile, large, utc_at(2026, 3, 3, 8), 7200)

        groups = ask(user, profile, "work_item").json()["groups"]

        assert [group["minutes"] for group in groups] == sorted([group["minutes"] for group in groups], reverse=True)
        assert "Large" in groups[0]["label"]
