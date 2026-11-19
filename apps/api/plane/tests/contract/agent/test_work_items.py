# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Projects and work items, as a connected app sees them.

The failure to guard against here does not look like an error. A rule applied almost
right shows up as "my colleague's private project is in the bot's answer", with every
status code 200. So each way a work item can be out of a person's sight has a case of
its own, and the hidden ones are checked to be indistinguishable from ones that do not
exist.
"""

# Python imports
from datetime import date, timedelta

# Third-party imports
import pytest
from django.utils import timezone

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import Issue, ProjectMember, State, WorkspaceMember
from plane.tests.contract.agent.conftest import bearer
from plane.tests.contract.agent.world import (
    at,
    comment,
    join,
    log_time,
    make_issue,
    make_project,
    make_user,
    make_workspace,
)

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

MEMBER, GUEST = ROLE.MEMBER.value, ROLE.GUEST.value


@pytest.fixture
def workspace(person):
    workspace = make_workspace()
    join(workspace, person)
    return workspace


@pytest.fixture
def colleague(workspace):
    user = make_user()
    join(workspace, user)
    return user


@pytest.fixture
def client(app, person):
    return bearer(app.link(person)["access_token"])


def refs(response):
    assert response.status_code == 200, response.content
    return sorted(item["ref"] for item in response.json()["results"])


class TestWhatIsVisible:
    def test_projects_the_person_belongs_to_and_no_others(self, client, workspace, person, colleague):
        make_project(workspace, "MINE", members=[(person, MEMBER), (colleague, MEMBER)])
        make_project(workspace, "THEIRS", members=[(colleague, MEMBER)])
        make_project(workspace, "GONE", members=[(person, MEMBER)], archived_at=timezone.now())
        body = client.get("/api/agent/v1/projects/").json()
        assert [(project["identifier"], project["role"]) for project in body["results"]] == [("MINE", "member")]

    def test_work_items_of_a_project_the_person_is_not_in_are_not_listed_or_fetched(
        self, client, workspace, person, colleague
    ):
        make_issue(make_project(workspace, "MINE", members=[(person, MEMBER)]), "Mine")
        hidden = make_issue(make_project(workspace, "SEC", members=[(colleague, MEMBER)]), "Salaries")
        response = client.get("/api/agent/v1/work-items/")
        assert refs(response) == ["MINE-1"] and "Salaries" not in response.content.decode()
        assert client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/SEC-1/").status_code == 404
        assert client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/{hidden.id}/").status_code == 404

    def test_a_hidden_work_item_looks_exactly_like_one_that_does_not_exist(self, client, workspace, colleague):
        make_issue(make_project(workspace, "SEC", members=[(colleague, MEMBER)]), "Salaries")
        hidden = client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/SEC-1/")
        absent = client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/SEC-99/")
        assert hidden.status_code == absent.status_code == 404
        assert hidden.json() == absent.json()

    def test_a_person_taken_out_of_a_project_loses_it_on_the_next_call(self, client, workspace, person):
        project = make_project(workspace, "MINE", members=[(person, MEMBER)])
        make_issue(project, "Mine")
        assert refs(client.get("/api/agent/v1/work-items/")) == ["MINE-1"]
        ProjectMember.objects.filter(project=project, member=person).update(is_active=False)
        assert refs(client.get("/api/agent/v1/work-items/")) == []
        assert client.get("/api/agent/v1/projects/").json()["results"] == []

    def test_a_person_who_has_left_the_workspace_sees_nothing_in_it(self, client, workspace, person):
        make_issue(make_project(workspace, "MINE", members=[(person, MEMBER)]), "Mine")
        WorkspaceMember.objects.filter(workspace=workspace, member=person).update(is_active=False)
        assert refs(client.get("/api/agent/v1/work-items/")) == []
        assert client.get("/api/agent/v1/projects/").json()["results"] == []

    def test_a_restricted_guest_sees_only_what_they_created(self, client, workspace, person, colleague):
        project = make_project(workspace, "GST", members=[(person, GUEST), (colleague, MEMBER)])
        make_issue(project, "Theirs", author=colleague)
        make_issue(project, "Mine", author=person)
        response = client.get("/api/agent/v1/work-items/")
        assert refs(response) == ["GST-2"] and "Theirs" not in response.content.decode()
        assert client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/GST-1/").status_code == 404
        assert client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/GST-2/").status_code == 200

    def test_a_guest_on_a_project_that_shows_guests_everything_sees_everything(
        self, client, workspace, person, colleague
    ):
        project = make_project(
            workspace, "OPEN", members=[(person, GUEST), (colleague, MEMBER)], guest_view_all_features=True
        )
        make_issue(project, "Theirs", author=colleague)
        assert refs(client.get("/api/agent/v1/work-items/")) == ["OPEN-1"]

    @pytest.mark.parametrize(
        "fields",
        [{"is_draft": True}, {"archived_at": date(2026, 1, 1)}],
        ids=["draft", "archived"],
    )
    def test_drafts_and_archived_items_are_left_out(self, client, workspace, person, fields):
        project = make_project(workspace, "MINE", members=[(person, MEMBER)])
        make_issue(project, "Listed")
        make_issue(project, "Left out", **fields)
        assert refs(client.get("/api/agent/v1/work-items/")) == ["MINE-1"]

    def test_work_awaiting_triage_and_deleted_work_are_left_out(self, client, workspace, person):
        project = make_project(workspace, "MINE", members=[(person, MEMBER)])
        make_issue(project, "Listed")
        make_issue(project, "Deleted").delete()
        triage = State.all_state_objects.create(
            project=project, workspace=workspace, name="Triage", group="triage", color="#000000"
        )
        Issue.objects.create(project=project, workspace=workspace, name="Triage", state=triage)
        assert refs(client.get("/api/agent/v1/work-items/")) == ["MINE-1"]

    def test_work_in_an_archived_project_is_left_out(self, client, workspace, person):
        project = make_project(workspace, "OLD", members=[(person, MEMBER)])
        make_issue(project, "Old work")
        project.archived_at = timezone.now()
        project.save()
        assert refs(client.get("/api/agent/v1/work-items/")) == []

    def test_a_connection_without_the_work_items_scope_sees_nothing(self, app, person):
        client = bearer(app.link(person, scope="profile time:read")["access_token"])
        for path in ("/api/agent/v1/projects/", "/api/agent/v1/work-items/"):
            assert client.get(path).status_code == 403


class TestListing:
    @pytest.fixture
    def project(self, workspace, person, colleague):
        return make_project(workspace, "PRJ", members=[(person, MEMBER), (colleague, MEMBER)])

    def test_my_work_is_the_work_assigned_to_me(self, client, project, person, colleague):
        make_issue(project, "Mine", assignees=[person])
        make_issue(project, "Theirs", assignees=[colleague])
        make_issue(project, "Nobody's")
        assert refs(client.get("/api/agent/v1/work-items/?assignee=me")) == ["PRJ-1"]

    def test_only_me_is_understood_as_an_assignee(self, client):
        assert client.get("/api/agent/v1/work-items/?assignee=someone-else").status_code == 400

    def test_filtering_by_what_stage_it_is_in(self, client, project, person):
        make_issue(project, "Doing", group="started", assignees=[person])
        make_issue(project, "Done", group="completed", assignees=[person])
        make_issue(project, "Later", group="backlog", assignees=[person])
        body = client.get("/api/agent/v1/work-items/?assignee=me&state_group=started,backlog")
        assert refs(body) == ["PRJ-1", "PRJ-3"]
        assert client.get("/api/agent/v1/work-items/?state_group=nonsense").status_code == 400

    def test_filtering_by_priority_and_due_date(self, client, project):
        make_issue(project, "Soon", priority="high", target_date=date(2026, 3, 5))
        make_issue(project, "Later", priority="low", target_date=date(2026, 4, 5))
        assert refs(client.get("/api/agent/v1/work-items/?priority=high")) == ["PRJ-1"]
        assert refs(client.get("/api/agent/v1/work-items/?due_before=2026-03-31")) == ["PRJ-1"]
        assert refs(client.get("/api/agent/v1/work-items/?due_after=2026-04-01")) == ["PRJ-2"]
        assert client.get("/api/agent/v1/work-items/?priority=urgent,whenever").status_code == 400

    def test_filtering_by_what_changed_needs_a_time_zone(self, client, project):
        make_issue(project, "Recent")
        before = (timezone.now() - timedelta(days=1)).isoformat()
        after = (timezone.now() + timedelta(days=1)).isoformat()
        assert refs(client.get("/api/agent/v1/work-items/", {"updated_since": before})) == ["PRJ-1"]
        assert refs(client.get("/api/agent/v1/work-items/", {"updated_since": after})) == []
        assert client.get("/api/agent/v1/work-items/?updated_since=2026-03-04T10:00:00").status_code == 400
        assert client.get("/api/agent/v1/work-items/?updated_since=yesterday").status_code == 400

    def test_searching_by_words(self, client, project):
        make_issue(project, "Fix the header")
        make_issue(project, "Write docs", description_html="<p>mentions the header too</p>")
        make_issue(project, "Unrelated")
        assert refs(client.get("/api/agent/v1/work-items/?q=header")) == ["PRJ-1", "PRJ-2"]

    def test_the_database_is_not_asked_to_order_by_whatever_the_app_likes(self, client, project):
        assert client.get("/api/agent/v1/work-items/?order_by=created_by__password").status_code == 400
        assert client.get("/api/agent/v1/work-items/?order_by=target_date").status_code == 200

    def test_paging(self, client, project):
        for number in range(5):
            make_issue(project, f"Task {number}")
        first = client.get("/api/agent/v1/work-items/?limit=2&order_by=created_at").json()
        assert first["count"] == 5 and len(first["results"]) == 2 and first["next_offset"] == 2
        last = client.get("/api/agent/v1/work-items/?limit=2&offset=4&order_by=created_at").json()
        assert len(last["results"]) == 1 and last["next_offset"] is None
        assert client.get("/api/agent/v1/work-items/?limit=0").status_code == 400
        assert client.get("/api/agent/v1/work-items/?limit=abc").status_code == 400
        assert client.get("/api/agent/v1/work-items/?limit=100000").json()["limit"] == 100

    def test_each_item_says_where_it_is_and_what_it_is_waiting_on(self, client, project, person, workspace):
        make_issue(project, "Task", assignees=[person], priority="high", target_date=date(2026, 3, 9))
        item = client.get("/api/agent/v1/work-items/").json()["results"][0]
        assert item["ref"] == "PRJ-1" and item["workspace"] == workspace.slug
        assert item["project"]["identifier"] == "PRJ" and item["state"]["group"] == "started"
        assert item["priority"] == "high" and item["target_date"] == "2026-03-09"
        assert item["assignees"][0]["id"] == str(person.id)
        assert item["url"].endswith(f"/{workspace.slug}/browse/PRJ-1/")

    def test_my_own_logged_time_is_reported_and_nobody_elses(self, client, project, person, colleague):
        issue = make_issue(project, "Task")
        log_time(issue, person, 90, at=at(2026, 3, 3, 9))
        log_time(issue, colleague, 600, at=at(2026, 3, 3, 9))
        item = client.get("/api/agent/v1/work-items/").json()["results"][0]
        assert item["my_logged_minutes"] == 90


class TestOneWorkItem:
    @pytest.fixture
    def project(self, workspace, person, colleague):
        return make_project(workspace, "PRJ", members=[(person, MEMBER), (colleague, MEMBER)])

    def test_by_reference_in_any_case_or_by_id(self, client, project, workspace):
        issue = make_issue(project, "Task")
        for ref in ("PRJ-1", "prj-1", str(issue.id)):
            assert client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/{ref}/").json()["id"] == str(
                issue.id
            )

    def test_a_reference_is_looked_for_only_in_the_workspace_named(self, client, project, person):
        other = make_workspace()
        join(other, person)
        make_issue(project, "Task")
        assert client.get(f"/api/agent/v1/workspaces/{other.slug}/work-items/PRJ-1/").status_code == 404

    def test_the_description_comes_as_plain_text_with_its_paragraphs_kept_apart(self, client, project, workspace):
        make_issue(
            project,
            "Task",
            description_html=(
                "<p>Call <b>Anna</b> &amp; ask</p><script>alert('x')</script><style>p{}</style>"
                "<p>Second<br>line</p><ul><li>one</li><li>two</li></ul>"
            ),
        )
        text = client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/PRJ-1/").json()["description"]
        assert text == "Call Anna & ask\nSecond\nline\n- one\n- two"

    def test_the_conversation_comes_in_order_with_who_said_what(self, client, project, workspace, colleague):
        issue = make_issue(project, "Task")
        comment(issue, "<p>First</p>", actor=colleague)
        comment(issue, "<p>Second</p>", actor=None)
        comments = client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/PRJ-1/").json()["comments"]
        assert [(item["text"], item["author"]) for item in comments] == [
            ("First", colleague.display_name),
            ("Second", None),
        ]

    def test_a_reference_that_is_neither_a_reference_nor_an_id_is_refused(self, client, project, workspace):
        assert client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/not-a-thing/").status_code == 400

    def test_a_reference_cannot_be_used_to_reach_another_projects_work(self, client, project, workspace, colleague):
        make_issue(make_project(workspace, "SEC", members=[(colleague, MEMBER)]), "Salaries")
        assert client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/SEC-1/").status_code == 404

    def test_the_number_of_work_items_in_a_project_does_not_leak_through_references(self, client, project, workspace):
        assert Issue.objects.count() == 0
        assert client.get(f"/api/agent/v1/workspaces/{workspace.slug}/work-items/PRJ-1/").status_code == 404
