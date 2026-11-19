# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Working days, hours, the running timer and leave, as a connected app sees them.

The point of these endpoints is a decision the app makes every morning: ask this
person for a plan, or do not. So the cases that matter are the ones where asking would
be wrong (a public holiday, a day off, a weekend) and the ones where telling would be
(why somebody is away, which can be sickness).
"""

# Python imports
from datetime import date

# Third-party imports
import pytest
from freezegun import freeze_time

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import IssueWorkLog
from plane.hr.models import HrAbsence, HrLeaveEntitlement, HrTimeEntry
from plane.tests.contract.agent.conftest import bearer
from plane.tests.contract.agent.world import (
    absence_type,
    absent,
    add_holiday,
    at,
    employ,
    join,
    log_time,
    make_issue,
    make_project,
    make_user,
    make_workspace,
)

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.fixture(autouse=True, scope="module")
def _load_the_urlconf():
    """Resolve the root URLconf before any test freezes the clock (see the HR tests for why)."""
    from django.urls import get_resolver

    get_resolver().url_patterns


@pytest.fixture
def workspace(person):
    workspace = make_workspace()
    join(workspace, person)
    return workspace


@pytest.fixture
def profile(workspace, person):
    return employ(workspace, person)


def call(app, person, path, scope="profile time:read"):
    tokens = app.link(person, scope=scope)
    return bearer(tokens["access_token"]).get(path)


# March 2026: Monday the 2nd ... Friday the 6th, Saturday the 7th.
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY = (date(2026, 3, day) for day in (2, 3, 4, 5, 6, 7))


class TestOneDay:
    def test_an_ordinary_weekday_is_a_working_day(self, app, person, profile):
        with freeze_time("2026-03-04 09:00:00+01:00"):
            body = call(app, person, "/api/agent/v1/me/day/").json()
        day = body["day"]
        assert body["employed"] is True and body["timezone"] == "Europe/Vienna"
        assert body["today"] == "2026-03-04" and day["is_today"] is True
        assert day["kind"] == "workday" and day["weekday"] == "wednesday"
        assert day["expects_work"] is True and day["expected_minutes"] == 480 and day["scheduled_minutes"] == 480
        assert day["holiday"] is None and day["absences"] == []

    def test_a_weekend_is_not(self, app, person, profile):
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-07").json()["day"]
        assert body["kind"] == "non_working_day" and body["expects_work"] is False

    def test_a_public_holiday_is_not_a_day_to_ask_for_a_plan(self, app, person, workspace, profile):
        add_holiday(workspace, WEDNESDAY, "Test Holiday")
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-04").json()["day"]
        assert body["kind"] == "public_holiday" and body["expects_work"] is False and body["expected_minutes"] == 0
        assert body["holiday"] == {"name": "Test Holiday", "fraction": 1.0}

    def test_half_a_public_holiday_leaves_half_a_day(self, app, person, workspace, profile):
        add_holiday(workspace, WEDNESDAY, "Half day", fraction="0.5")
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-04").json()["day"]
        assert body["kind"] == "half_public_holiday" and body["expects_work"] is True
        assert body["expected_minutes"] == 240

    def test_a_holiday_on_a_day_the_person_never_works_changes_nothing(self, app, person, workspace):
        employ(workspace, person, days=(1, 2, 3, 4))  # no Mondays
        add_holiday(workspace, MONDAY)
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-02").json()["day"]
        assert body["kind"] == "non_working_day" and body["expects_work"] is False

    def test_approved_leave_is_a_day_off(self, app, person, profile):
        absent(profile, THURSDAY)
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-05").json()["day"]
        assert body["kind"] == "absence" and body["expects_work"] is False
        assert body["absences"] == [{"granularity": "full_day", "half": None, "minutes": None}]

    def test_unpaid_leave_is_a_day_off_too(self, app, person, workspace, profile):
        absent(profile, THURSDAY, kind=absence_type(workspace, "unbezahlt", "Unpaid leave", credits_actual=False))
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-05").json()["day"]
        assert body["kind"] == "absence" and body["expects_work"] is False

    def test_half_a_day_off_leaves_half_a_day(self, app, person, profile):
        absent(profile, FRIDAY, granularity=HrAbsence.Granularity.HALF_DAY, start_half=10, end_half=10)
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-06").json()["day"]
        assert body["kind"] == "partial_absence" and body["expected_minutes"] == 240
        assert body["absences"][0]["granularity"] == "half_day" and body["absences"][0]["half"] == "morning"

    def test_a_request_nobody_has_approved_is_not_a_day_off(self, app, person, profile):
        absent(profile, THURSDAY, state=HrAbsence.State.REQUESTED)
        absent(profile, THURSDAY, state=HrAbsence.State.REJECTED)
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-05").json()["day"]
        assert body["kind"] == "workday" and body["absences"] == []

    def test_why_somebody_is_away_is_not_told_without_the_leave_scope(self, app, person, workspace, profile):
        """The reason for a sick day is health information. 'Away' is enough to know not to ask for a plan."""
        sick = absence_type(workspace, "krankenstand", "Sick leave", consumes_leave_entitlement=False)
        absent(profile, THURSDAY, kind=sick, reason="chemotherapy")

        plain = call(app, person, "/api/agent/v1/me/day/?date=2026-03-05", scope="profile time:read")
        assert plain.json()["day"]["kind"] == "absence"
        assert "type" not in plain.json()["day"]["absences"][0]
        assert "Sick" not in plain.content.decode() and "chemotherapy" not in plain.content.decode()

        detailed = call(app, person, "/api/agent/v1/me/day/?date=2026-03-05", scope="profile time:read leave:read")
        assert detailed.json()["day"]["absences"][0]["type"] == {"code": "krankenstand", "name": "Sick leave"}
        assert "chemotherapy" not in detailed.content.decode(), "the free-text reason is never given"

    def test_today_is_where_the_person_is_not_where_the_server_is(self, app, person, profile):
        # 23:30 UTC on the 4th is half past midnight on the 5th in Vienna.
        with freeze_time("2026-03-04 23:30:00+00:00"):
            body = call(app, person, "/api/agent/v1/me/day/").json()
        assert body["today"] == "2026-03-05" and body["day"]["weekday"] == "thursday"

    def test_what_has_been_worked_so_far_is_reported(self, app, person, workspace, profile):
        issue = make_issue(make_project(workspace, members=[(person, ROLE.MEMBER.value)]), "Task")
        log_time(issue, person, 90, at=at(2026, 3, 4, 10))
        HrTimeEntry.objects.create(workspace=workspace, profile=profile, entry_date=WEDNESDAY, minutes=30)
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-04").json()["day"]
        assert body["worked_minutes"] == 120

    def test_nobody_is_told_about_a_person_without_an_employment_record(self, app, person, workspace):
        body = call(app, person, "/api/agent/v1/me/day/?date=2026-03-04").json()
        assert body["employed"] is False and body["day"] is None

    def test_a_person_who_has_left_has_no_working_days(self, app, person, workspace, profile):
        profile.is_active = False
        profile.save()
        assert call(app, person, "/api/agent/v1/me/day/").json()["employed"] is False

    def test_no_schedule_is_a_gap_in_the_records_not_a_day_off(self, app, person, workspace):
        employ(workspace, person, schedule=False)
        day = call(app, person, "/api/agent/v1/me/day/?date=2026-03-04").json()["day"]
        assert day["has_schedule"] is False and day["expects_work"] is False

    @pytest.mark.parametrize("value", ["tomorrow", "2026-13-01", "04.03.2026", "1500-01-01", "2026-03-04T10:00"])
    def test_a_date_that_is_not_a_date_is_refused(self, app, person, profile, value):
        response = call(app, person, f"/api/agent/v1/me/day/?date={value}")
        assert response.status_code == 400 and response.json()["error"] == "invalid_request"

    def test_it_needs_the_time_scope(self, app, person, profile):
        response = call(app, person, "/api/agent/v1/me/day/", scope="profile")
        assert response.status_code == 403 and response.json()["scope"] == "time:read"


class TestSpanOfDays:
    def test_it_tells_which_days_to_expect_work_on(self, app, person, workspace, profile):
        add_holiday(workspace, WEDNESDAY)
        absent(profile, THURSDAY)
        body = call(app, person, "/api/agent/v1/me/days/?from=2026-03-02&to=2026-03-08").json()
        kinds = [(day["date"][-2:], day["kind"]) for day in body["days"]]
        assert kinds == [
            ("02", "workday"),
            ("03", "workday"),
            ("04", "public_holiday"),
            ("05", "absence"),
            ("06", "workday"),
            ("07", "non_working_day"),
            ("08", "non_working_day"),
        ]
        assert body["working_days"] == 3 and body["expected_minutes"] == 3 * 480

    def test_a_week_from_today_is_the_default(self, app, person, profile):
        with freeze_time("2026-03-04 09:00:00+01:00"):
            body = call(app, person, "/api/agent/v1/me/days/").json()
        assert body["from"] == "2026-03-04" and body["to"] == "2026-03-10" and len(body["days"]) == 7

    @pytest.mark.parametrize(
        "query",
        ["from=2026-03-10&to=2026-03-02", "from=2026-01-01&to=2026-12-31", "from=nonsense"],
    )
    def test_an_impossible_span_is_refused(self, app, person, profile, query):
        assert call(app, person, f"/api/agent/v1/me/days/?{query}").status_code == 400

    def test_the_longest_span_is_accepted(self, app, person, profile):
        assert call(app, person, "/api/agent/v1/me/days/?from=2026-03-01&to=2026-05-31").status_code == 200

    def test_nobody_employed_gets_an_empty_answer(self, app, person, workspace):
        body = call(app, person, "/api/agent/v1/me/days/?from=2026-03-02&to=2026-03-08").json()
        assert body["employed"] is False and body["days"] == []


class TestHours:
    @pytest.fixture
    def project(self, workspace, person):
        return make_project(workspace, "ATTN", members=[(person, ROLE.MEMBER.value)])

    def test_hours_are_summed_per_day_the_way_the_month_sums_them(self, app, person, workspace, profile, project):
        first, second = make_issue(project, "First"), make_issue(project, "Second")
        # Two entries of 100 s on one project and day: the ledger rounds the 200 s once (3 minutes),
        # where rounding each would give 2.
        for issue in (first, second):
            IssueWorkLog.objects.create(
                issue=issue,
                project=project,
                workspace=workspace,
                logged_by=person,
                duration=100,
                started_at=at(2026, 3, 3, 9),
                logged_at=at(2026, 3, 3, 9),
            )
        HrTimeEntry.objects.create(workspace=workspace, profile=profile, entry_date=TUESDAY, minutes=15)

        body = call(
            app, person, "/api/agent/v1/me/time/?from=2026-03-03&to=2026-03-03", scope="profile time:read"
        ).json()

        assert body["days"] == [{"date": "2026-03-03", "minutes": 18, "work_item_minutes": 3, "other_minutes": 15}]
        assert body["total_minutes"] == 18
        assert body["work_items"] is None, "which work items is the work-items scope's business"

    def test_the_work_items_are_named_when_the_person_allowed_it(self, app, person, profile, project):
        issue = make_issue(project, "Fix the header")
        log_time(issue, person, 60, at=at(2026, 3, 3, 9))
        log_time(issue, person, 30, at=at(2026, 3, 4, 9))
        body = call(
            app,
            person,
            "/api/agent/v1/me/time/?from=2026-03-02&to=2026-03-08",
            scope="profile time:read work_items:read",
        ).json()
        assert [(item["minutes"], item["work_item"]["ref"]) for item in body["work_items"]] == [(90, "ATTN-1")]
        assert body["work_items"][0]["work_item"]["my_logged_minutes"] == 90

    def test_time_on_something_no_longer_visible_counts_but_is_not_named(
        self, app, person, workspace, profile, project
    ):
        elsewhere = make_project(workspace, "SEC", members=[])
        secret = make_issue(elsewhere, "Confidential")
        log_time(secret, person, 45, at=at(2026, 3, 3, 9))
        response = call(
            app,
            person,
            "/api/agent/v1/me/time/?from=2026-03-02&to=2026-03-08",
            scope="profile time:read work_items:read",
        )
        body = response.json()
        assert body["total_minutes"] == 45
        assert body["work_items"] == [{"minutes": 45, "entries": 1, "work_item": None}]
        assert "Confidential" not in response.content.decode()

    def test_hours_belong_to_the_day_where_the_person_is(self, app, person, profile, project):
        issue = make_issue(project, "Late")
        # 23:30 UTC on the 3rd is 00:30 on the 4th in Vienna.
        log_time(issue, person, 10, at=at(2026, 3, 3, 23, 30))
        body = call(app, person, "/api/agent/v1/me/time/?from=2026-03-02&to=2026-03-08").json()
        assert [day["date"] for day in body["days"]] == ["2026-03-04"]

    def test_only_the_connected_person_s_hours_are_counted(self, app, person, workspace, profile, project):
        issue = make_issue(project, "Shared")
        colleague = make_user()
        join(workspace, colleague)
        log_time(issue, colleague, 120, at=at(2026, 3, 3, 9))
        body = call(app, person, "/api/agent/v1/me/time/?from=2026-03-02&to=2026-03-08").json()
        assert body["total_minutes"] == 0

    def test_a_week_back_from_today_is_the_default(self, app, person, profile):
        with freeze_time("2026-03-10 09:00:00+01:00"):
            body = call(app, person, "/api/agent/v1/me/time/").json()
        assert body["from"] == "2026-03-04" and body["to"] == "2026-03-10"


class TestTimer:
    def test_the_running_timer_and_what_it_is_on(self, app, person, workspace, profile):
        project = make_project(workspace, "ATTN", members=[(person, ROLE.MEMBER.value)])
        issue = make_issue(project, "Fix the header")
        with freeze_time("2026-03-04 10:00:00+00:00"):
            log_time(issue, person, 25, at=at(2026, 3, 4, 10), running=True)
            body = call(app, person, "/api/agent/v1/me/timer/", scope="profile time:read work_items:read").json()
        assert body["running"] is True
        assert body["timer"]["elapsed_minutes"] == 25
        assert body["timer"]["work_item"]["ref"] == "ATTN-1" and body["timer"]["work_item"]["name"] == "Fix the header"

    def test_without_the_work_items_scope_it_does_not_say_what_it_is_on(self, app, person, workspace, profile):
        project = make_project(workspace, "ATTN", members=[(person, ROLE.MEMBER.value)])
        log_time(make_issue(project, "Secret plan"), person, 5, at=at(2026, 3, 4, 10), running=True)
        response = call(app, person, "/api/agent/v1/me/timer/")
        assert response.json()["running"] is True and response.json()["timer"]["work_item"] is None
        assert "Secret plan" not in response.content.decode()

    def test_a_timer_on_something_the_person_can_no_longer_see_is_not_named(self, app, person, workspace, profile):
        elsewhere = make_project(workspace, "SEC", members=[])
        log_time(make_issue(elsewhere, "Confidential"), person, 5, at=at(2026, 3, 4, 10), running=True)
        response = call(app, person, "/api/agent/v1/me/timer/", scope="profile time:read work_items:read")
        assert response.json()["running"] is True and response.json()["timer"]["work_item"] is None

    def test_no_timer_is_a_plain_answer(self, app, person, profile):
        assert call(app, person, "/api/agent/v1/me/timer/").json() == {"running": False, "timer": None}


class TestLeave:
    def test_what_is_left_of_the_leave_year(self, app, person, workspace, profile):
        HrLeaveEntitlement.objects.create(
            workspace=workspace,
            profile=profile,
            leave_year_start=date(2026, 1, 1),
            leave_year_end=date(2026, 12, 31),
            entitlement_minutes=25 * 480,
        )
        absent(profile, date(2026, 2, 9), date(2026, 2, 13))  # a week of leave
        with freeze_time("2026-03-04 09:00:00+01:00"):
            body = call(app, person, "/api/agent/v1/me/leave/", scope="profile leave:read").json()
        assert body["leave"]["granted_minutes"] == 25 * 480
        assert body["leave"]["taken_minutes"] == 5 * 480
        assert body["leave"]["remaining_minutes"] == 20 * 480

    def test_it_needs_the_leave_scope(self, app, person, profile):
        response = call(app, person, "/api/agent/v1/me/leave/", scope="profile time:read")
        assert response.status_code == 403 and response.json()["scope"] == "leave:read"

    def test_no_entitlement_on_record_is_none_not_zero(self, app, person, profile):
        body = call(app, person, "/api/agent/v1/me/leave/", scope="profile leave:read").json()
        assert body["leave"] is None

    def test_the_booked_absences_are_listed_without_their_reasons(self, app, person, workspace, profile):
        absent(profile, date(2026, 3, 9), date(2026, 3, 13), reason="private matter")
        absent(profile, date(2026, 3, 16), state=HrAbsence.State.REQUESTED)
        response = call(
            app, person, "/api/agent/v1/me/absences/?from=2026-03-01&to=2026-03-31", scope="profile leave:read"
        )
        body = response.json()
        assert [(item["start_date"], item["end_date"], item["type"]["code"]) for item in body["absences"]] == [
            ("2026-03-09", "2026-03-13", "urlaub")
        ]
        assert "private matter" not in response.content.decode()

    def test_nobody_employed_has_no_leave(self, app, person, workspace):
        assert call(app, person, "/api/agent/v1/me/leave/", scope="profile leave:read").json()["employed"] is False
