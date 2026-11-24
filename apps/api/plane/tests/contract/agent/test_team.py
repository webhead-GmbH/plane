# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A manager's app looking at the people they manage.

Everything here is about people who approved nothing, so the tests that matter are the ones
that say what an app must *not* learn: why a colleague is away, anything in a project the
manager cannot see, anything at all once the manager stops being one.
"""

# Python imports
from datetime import date
from uuid import uuid4

# Third-party imports
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from freezegun import freeze_time

# Module imports
from plane.agent.models import AgentAuditLog
from plane.agent.scopes import DEFAULT_SCOPES, SCOPES, describe
from plane.app.permissions import ROLE
from plane.db.models import ProjectMember, User
from plane.hr.models import HrEmploymentProfile, HrTimeEntry
from plane.license.models import Instance, InstanceAdmin
from plane.tests.contract.agent.conftest import ALL_SCOPES, bearer
from plane.tests.contract.agent.world import (
    absence_type,
    absent,
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

TEAM = "/api/agent/v1/team/"
WORKLOAD = "/api/agent/v1/team/workload/"
# March 2026: Monday the 2nd to Friday the 6th.
WEEK = "from=2026-03-02&to=2026-03-06"
TUESDAY, WEDNESDAY = date(2026, 3, 3), date(2026, 3, 4)
SICK_NOTE = "Chemotherapy on Tuesday"
NOW = "2026-03-04 09:00:00+01:00"


@pytest.fixture(autouse=True, scope="module")
def _load_the_urlconf():
    from django.urls import get_resolver

    get_resolver().url_patterns


@pytest.fixture
def workspace():
    return make_workspace()


def colleague(workspace, name, *, manager=False, **fields):
    user = make_user(first_name=name, last_name="Colleague", display_name=name, **fields)
    join(workspace, user)
    profile = employ(workspace, user)
    if manager:
        profile.is_hr_manager = True
        profile.save(update_fields=["is_hr_manager"])
    return user, profile


@pytest.fixture
def boss(workspace):
    return colleague(workspace, "Boss", manager=True)


@pytest.fixture
def ana(workspace):
    return colleague(workspace, "Ana")


@pytest.fixture
def ben(workspace):
    return colleague(workspace, "Ben")


@pytest.fixture
def project(workspace, boss, ana, ben):
    return make_project(workspace, "TEA", members=[(user, ROLE.MEMBER.value) for user, _profile in (boss, ana, ben)])


def ask(app, user, path, scope=ALL_SCOPES):
    tokens = app.link(user, scope=scope)
    return bearer(tokens["access_token"]).get(path)


def manager_client(app, boss, scope=ALL_SCOPES):
    return bearer(app.link(boss[0], scope=scope)["access_token"])


def by_name(body):
    return {row["display_name"]: row for row in body["results"]}


class TestTheScopeIsNeverGivenByDefault:
    def test_it_is_marked_as_showing_other_people(self):
        scope = SCOPES["team:read"]
        assert scope.others is True and scope.writes is False
        assert [row["others"] for row in describe(["team:read", "profile"])] == [True, False]

    def test_an_app_registered_without_naming_scopes_does_not_get_it(self):
        assert "team:read" not in DEFAULT_SCOPES
        # What the old name meant, kept for code written against the first release.
        from plane.agent.scopes import READ_ONLY_SCOPES

        assert READ_ONLY_SCOPES == DEFAULT_SCOPES

    def test_the_command_registers_apps_without_it_unless_it_is_named(self):
        from django.core.management import call_command

        from plane.agent.models import AgentClient

        call_command("agent_client", "create", "--name", "Plain", "--redirect-uri", "https://bot.example.com/cb")
        assert "team:read" not in AgentClient.objects.get(name="Plain").allowed_scopes
        call_command(
            "agent_client",
            "create",
            "--name",
            "Reporting",
            "--redirect-uri",
            "https://bot.example.com/cb",
            "--scope",
            "profile",
            "--scope",
            "team:read",
        )
        assert AgentClient.objects.get(name="Reporting").allowed_scopes == ["profile", "team:read"]


class TestWhoMayLook:
    def test_a_connection_without_the_scope_is_told_so(self, app, boss):
        response = ask(app, boss[0], TEAM, scope="profile time:read work_items:read")
        assert response.status_code == 403
        assert response.json()["error"] == "insufficient_scope" and response.json()["scope"] == "team:read"

    def test_somebody_who_is_not_a_manager_sees_nothing(self, app, ana):
        response = ask(app, ana[0], TEAM)
        assert response.status_code == 403 and response.json()["error"] == "not_a_manager"
        assert ask(app, ana[0], WORKLOAD).status_code == 403

    def test_a_manager_who_stops_being_one_loses_the_view_on_the_next_call(self, app, boss, ana):
        client = manager_client(app, boss)
        assert client.get(TEAM).status_code == 200
        HrEmploymentProfile.objects.filter(pk=boss[1].pk).update(is_hr_manager=False)
        assert client.get(TEAM).status_code == 403
        assert client.get(WORKLOAD).status_code == 403
        assert client.get(f"{TEAM}{ana[0].id}/work-items/").status_code == 403

    def test_somebody_who_leaves_the_company_loses_it_too(self, app, boss):
        client = manager_client(app, boss)
        HrEmploymentProfile.objects.filter(pk=boss[1].pk).update(is_active=False)
        assert client.get(TEAM).status_code == 403

    def test_an_instance_administrator_counts_as_a_manager_as_in_the_hr_module(self, app, ana):
        admin = make_user()
        instance = Instance.objects.first() or Instance.objects.create(
            instance_name="test", instance_id=uuid4().hex, current_version="1.0.0", last_checked_at=timezone.now()
        )
        InstanceAdmin.objects.create(instance=instance, user=admin)
        response = ask(app, admin, TEAM)
        assert response.status_code == 200
        assert [row["display_name"] for row in response.json()["results"]] == ["Ana"]

    def test_a_team_call_needs_a_token_not_a_session(self, app, boss, client):
        client.force_login(boss[0])
        assert client.get(TEAM).status_code == 401


class TestThePeople:
    def test_lists_the_people_who_work_here_now(self, app, workspace, boss, ana, ben):
        gone_user, gone = colleague(workspace, "Gone")
        HrEmploymentProfile.objects.filter(pk=gone.pk).update(is_active=False)
        locked_user, _ = colleague(workspace, "Locked")
        User.objects.filter(pk=locked_user.pk).update(is_active=False)
        colleague(workspace, "Robot", is_bot=True)

        body = ask(app, boss[0], TEAM).json()

        assert [row["display_name"] for row in body["results"]] == ["Ana", "Ben", "Boss"]
        assert body["count"] == 3 and body["next_offset"] is None
        ana_row = by_name(body)["Ana"]
        assert ana_row["id"] == str(ana[0].id) and ana_row["timezone"] == "Europe/Vienna"
        # Only what an app needs to tell people apart.
        assert set(ana_row) == {"id", "display_name", "timezone"}

    def test_pages(self, app, workspace, boss, ana, ben):
        client = manager_client(app, boss)
        first = client.get(f"{TEAM}?limit=2").json()
        assert [row["display_name"] for row in first["results"]] == ["Ana", "Ben"] and first["next_offset"] == 2
        second = client.get(f"{TEAM}?limit=2&offset=2").json()
        assert [row["display_name"] for row in second["results"]] == ["Boss"] and second["next_offset"] is None


@freeze_time(NOW)
class TestRoomAndHours:
    def test_expected_hours_follow_each_persons_own_days(self, app, boss, ana, ben):
        body = ask(app, boss[0], f"{WORKLOAD}?{WEEK}").json()
        assert body["from"] == "2026-03-02" and body["to"] == "2026-03-06"
        row = by_name(body)["Ana"]
        assert row["capacity"] == {"expected_minutes": 2400, "working_days": 5, "days_away": 0, "has_schedule": True}
        assert row["timezone"] == "Europe/Vienna"

    def test_a_day_off_takes_hours_away_without_saying_why(self, app, workspace, boss, ana, ben):
        sick = absence_type(workspace, code="krank", name="Sick leave")
        absent(ben[1], TUESDAY, WEDNESDAY, kind=sick, reason=SICK_NOTE)
        client = manager_client(app, boss)

        response = client.get(f"{WORKLOAD}?{WEEK}&include=days")

        row = by_name(response.json())["Ben"]
        assert row["capacity"]["expected_minutes"] == 3 * 480
        assert row["capacity"]["working_days"] == 3 and row["capacity"]["days_away"] == 2
        days = {day["date"]: day for day in row["capacity"]["days"]}
        assert days["2026-03-03"]["kind"] == "absence" and days["2026-03-03"]["expects_work"] is False
        assert set(days["2026-03-03"]) == {
            "date",
            "weekday",
            "kind",
            "expects_work",
            "scheduled_minutes",
            "expected_minutes",
        }
        # The app was granted every scope, leave:read among them, and still never hears why.
        text = response.content.decode().lower()
        for secret in ("krank", "sick", "chemotherapy", SICK_NOTE.lower()):
            assert secret not in text
        assert "absences" not in text and "type" not in text

    def test_days_are_only_given_when_asked_for(self, app, boss, ana):
        row = by_name(ask(app, boss[0], f"{WORKLOAD}?{WEEK}").json())["Ana"]
        assert "days" not in row["capacity"]

    def test_hours_worked_count_in_the_persons_own_days(self, app, workspace, boss, ana, project):
        issue = make_issue(project, "Report", assignees=[ana[0]])
        log_time(issue, ana[0], 90, at=at(2026, 3, 3, 12))
        # 23:30 UTC on Wednesday the 4th is already Thursday the 5th in Vienna: outside Mon–Wed, inside the week.
        log_time(issue, ana[0], 30, at=at(2026, 3, 4, 23, 30))
        HrTimeEntry.objects.create(workspace=workspace, profile=ana[1], entry_date=WEDNESDAY, minutes=45)

        client = manager_client(app, boss)
        week = by_name(client.get(f"{WORKLOAD}?{WEEK}").json())["Ana"]["worked"]
        assert week == {"total_minutes": 165, "work_item_minutes": 120, "other_minutes": 45}
        until_wednesday = by_name(client.get(f"{WORKLOAD}?from=2026-03-02&to=2026-03-04").json())["Ana"]["worked"]
        assert until_wednesday == {"total_minutes": 135, "work_item_minutes": 90, "other_minutes": 45}

    def test_a_running_timer_is_a_yes_or_no_and_nothing_more(self, app, boss, ana, ben, project):
        issue = make_issue(project, "Secret client launch", assignees=[ana[0]])
        log_time(issue, ana[0], 20, at=at(2026, 3, 4, 7), running=True)
        response = ask(app, boss[0], f"{WORKLOAD}?{WEEK}")
        rows = by_name(response.json())
        assert rows["Ana"]["timer_running"] is True and rows["Ben"]["timer_running"] is False
        assert "Secret client launch" not in response.content.decode()


@freeze_time(NOW)
class TestOpenWork:
    def test_it_is_counted_without_being_named(self, app, workspace, boss, ana, project):
        today = date(2026, 3, 4)
        make_issue(project, "Late", assignees=[ana[0]], target_date=date(2026, 3, 2), priority="urgent")
        make_issue(project, "Due Friday", assignees=[ana[0]], target_date=date(2026, 3, 6), group="unstarted")
        make_issue(project, "Due next month", assignees=[ana[0]], target_date=date(2026, 4, 1), priority="high")
        make_issue(project, "Whenever", assignees=[ana[0]], group="backlog")
        make_issue(project, "Finished", assignees=[ana[0]], group="completed", target_date=today)
        make_issue(project, "Dropped", assignees=[ana[0]], group="cancelled")

        response = ask(app, boss[0], f"{WORKLOAD}?from=2026-03-04&to=2026-03-10")

        assert by_name(response.json())["Ana"]["open_work"] == {
            "count": 4,
            "in_progress": 2,
            "overdue": 1,
            "due_in_span": 1,
            "due_later": 1,
            "no_due_date": 1,
            "urgent_or_high": 2,
        }
        for title in ("Late", "Due Friday", "Whenever"):
            assert title not in response.content.decode()

    def test_work_in_a_project_the_manager_is_not_in_is_not_counted(self, app, workspace, boss, ana):
        elsewhere = make_project(workspace, "SEC", members=[(ana[0], ROLE.MEMBER.value)])
        make_issue(elsewhere, "Confidential", assignees=[ana[0]], target_date=date(2026, 3, 5))

        row = by_name(ask(app, boss[0], f"{WORKLOAD}?{WEEK}").json())["Ana"]

        assert row["open_work"]["count"] == 0

    def test_somebody_who_left_the_project_no_longer_carries_its_work(self, app, workspace, boss, ana, project):
        make_issue(project, "Handed over", assignees=[ana[0]])
        ProjectMember.objects.filter(project=project, member=ana[0]).update(is_active=False)

        assert by_name(ask(app, boss[0], f"{WORKLOAD}?{WEEK}").json())["Ana"]["open_work"]["count"] == 0

    def test_two_people_on_one_item_each_carry_it(self, app, boss, ana, ben, project):
        make_issue(project, "Pair work", assignees=[ana[0], ben[0]])
        rows = by_name(ask(app, boss[0], f"{WORKLOAD}?{WEEK}").json())
        assert rows["Ana"]["open_work"]["count"] == 1 and rows["Ben"]["open_work"]["count"] == 1


@freeze_time(NOW)
class TestNarrowingAndLimits:
    def test_a_span_longer_than_a_month_is_refused(self, app, boss):
        assert ask(app, boss[0], f"{WORKLOAD}?from=2026-03-01&to=2026-04-01").status_code == 400
        assert ask(app, boss[0], f"{WORKLOAD}?from=2026-03-01&to=2026-03-31").status_code == 200

    def test_the_default_span_is_the_coming_week(self, app, boss, ana):
        body = ask(app, boss[0], WORKLOAD).json()
        assert (body["from"], body["to"]) == ("2026-03-04", "2026-03-10")

    def test_people_can_be_named(self, app, boss, ana, ben):
        client = manager_client(app, boss)
        body = client.get(f"{WORKLOAD}?{WEEK}&user={ben[0].id}").json()
        assert [row["display_name"] for row in body["results"]] == ["Ben"] and body["count"] == 1

    def test_a_bad_user_id_is_refused_and_an_unknown_one_matches_nobody(self, app, boss):
        client = manager_client(app, boss)
        assert client.get(f"{WORKLOAD}?user=not-an-id").status_code == 400
        assert client.get(f"{WORKLOAD}?user={uuid4()}").json()["results"] == []
        too_many = ",".join(str(uuid4()) for _ in range(26))
        assert client.get(f"{WORKLOAD}?user={too_many}").status_code == 400

    def test_a_page_never_holds_more_than_the_cap(self, app, boss):
        assert ask(app, boss[0], f"{WORKLOAD}?limit=500").json()["limit"] == 25

    def test_each_extra_person_costs_a_small_fixed_number_of_queries(self, app, workspace, boss, ana, ben):
        client = manager_client(app, boss)

        def queries(ids):
            with CaptureQueriesContext(connection) as context:
                assert client.get(f"{WORKLOAD}?{WEEK}&user={ids}").status_code == 200
            return len(context)

        one = queries(ana[0].id)
        more = [colleague(workspace, f"Extra {number}")[0].id for number in range(4)]
        five = queries(",".join(str(item) for item in [ana[0].id, ben[0].id, *more[:3]]))
        assert (five - one) / 4 <= 8


@freeze_time(NOW)
class TestOnePersonsWork:
    def test_lists_what_the_manager_can_see_of_it(self, app, workspace, boss, ana, project):
        mine = make_issue(project, "Shared project task", assignees=[ana[0]], target_date=date(2026, 3, 6))
        make_issue(project, "Not hers", assignees=[boss[0]])
        elsewhere = make_project(workspace, "SEC", members=[(ana[0], ROLE.MEMBER.value)])
        make_issue(elsewhere, "Confidential", assignees=[ana[0]])
        log_time(mine, ana[0], 90, at=at(2026, 3, 3, 12))
        log_time(mine, boss[0], 15, at=at(2026, 3, 3, 13))

        response = ask(app, boss[0], f"{TEAM}{ana[0].id}/work-items/")

        assert response.status_code == 200
        body = response.json()
        assert [item["name"] for item in body["results"]] == ["Shared project task"]
        assert body["person"] == {"id": str(ana[0].id), "display_name": "Ana"}
        item = body["results"][0]
        # The hours are hers, not the manager's; and the field does not claim to be the viewer's.
        assert item["person_logged_minutes"] == 90 and "my_logged_minutes" not in item
        assert "Confidential" not in response.content.decode()

    def test_takes_the_same_filters_as_the_apps_own_list(self, app, boss, ana, project):
        make_issue(project, "Late", assignees=[ana[0]], target_date=date(2026, 3, 1), group="unstarted")
        make_issue(project, "Fine", assignees=[ana[0]], target_date=date(2026, 3, 30), group="started")
        client = manager_client(app, boss)
        late = client.get(f"{TEAM}{ana[0].id}/work-items/?due_before=2026-03-03&state_group=unstarted")
        assert [item["name"] for item in late.json()["results"]] == ["Late"]
        assert client.get(f"{TEAM}{ana[0].id}/work-items/?state_group=nonsense").status_code == 400

    def test_it_needs_the_work_item_scope_as_well(self, app, boss, ana):
        response = ask(app, boss[0], f"{TEAM}{ana[0].id}/work-items/", scope="profile team:read time:read")
        assert response.status_code == 403
        assert response.json()["error"] == "insufficient_scope" and response.json()["scope"] == "work_items:read"

    def test_a_person_who_is_not_on_the_team_is_not_found(self, app, workspace, boss):
        gone_user, gone = colleague(workspace, "Gone")
        HrEmploymentProfile.objects.filter(pk=gone.pk).update(is_active=False)
        outsider = make_user()
        client = manager_client(app, boss)
        for user_id in (gone_user.id, outsider.id, uuid4()):
            assert client.get(f"{TEAM}{user_id}/work-items/").status_code == 404
        assert client.get(f"{TEAM}nobody/work-items/").status_code == 400

    def test_the_apps_own_list_still_refuses_somebody_elses_id(self, app, boss, ana):
        response = ask(app, boss[0], f"/api/agent/v1/work-items/?assignee={ana[0].id}")
        assert response.status_code == 400


@freeze_time(NOW)
class TestTheLogSaysWhoseInformationWasRead:
    def test_the_people_are_named_by_id_and_nothing_else(self, app, boss, ana, ben, project):
        make_issue(project, "Board prep", assignees=[ana[0]])
        client = manager_client(app, boss)
        client.get(f"{WORKLOAD}?{WEEK}")
        client.get(f"{TEAM}{ana[0].id}/work-items/")

        rows = {
            row.path: row for row in AgentAuditLog.objects.filter(event="api", path__startswith="/api/agent/v1/team/")
        }
        workload = rows["/api/agent/v1/team/workload/"]
        one_person = rows[f"/api/agent/v1/team/{ana[0].id}/work-items/"]
        assert workload.detail["subjects"] == sorted([str(ana[0].id), str(ben[0].id), str(boss[0].id)])
        assert one_person.detail["subjects"] == [str(ana[0].id)]
        assert "Board prep" not in str([row.detail for row in rows.values()])

    def test_a_call_that_reads_nobody_has_no_subjects(self, app, boss):
        client = manager_client(app, boss)
        client.get("/api/agent/v1/me/")
        assert "subjects" not in AgentAuditLog.objects.get(event="api", path="/api/agent/v1/me/").detail
