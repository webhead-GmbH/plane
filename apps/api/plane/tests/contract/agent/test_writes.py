# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Creating and changing work, commenting, and tracking time through a connected app.

A write is where an app stops watching and starts acting in somebody's name, so the cases
here are the ones that would make that go wrong: a retry that does it twice, a field the app
was never meant to set, a person acting where their role forbids it, a timer rule or a
settled month quietly bypassed, and text from a language model arriving as markup.
"""

# Python imports
import uuid
from datetime import date, timedelta

# Third-party imports
import pytest
from freezegun import freeze_time

# Module imports
from plane.agent.models import AgentAuditLog, AgentIdempotencyKey
from plane.app.permissions import ROLE
from plane.agent.services.work_items import description_version
from plane.db.models import Issue, IssueComment, IssueDescriptionVersion, IssueWorkLog, State
from plane.hr.models import HrPeriod
from plane.tests.contract.agent.conftest import bearer, client_with
from plane.tests.contract.agent.world import (
    employ,
    join,
    make_issue,
    make_label,
    make_project,
    make_state,
    make_user,
    make_workspace,
)

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

MEMBER, GUEST, ADMIN = ROLE.MEMBER.value, ROLE.GUEST.value, ROLE.ADMIN.value
WRITE = "profile time:read work_items:read work_items:write time:write"


@pytest.fixture(autouse=True, scope="module")
def _load_the_urlconf():
    from django.urls import get_resolver

    get_resolver().url_patterns


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
def project(workspace, person, colleague):
    project = make_project(workspace, "PRJ", members=[(person, MEMBER), (colleague, MEMBER)])
    State.objects.create(
        project=project, workspace=workspace, name="Backlog", group="backlog", default=True, color="#000000"
    )
    return project


@pytest.fixture
def client(app, person):
    return client_with(app, person, WRITE)


def key():
    return "key-" + uuid.uuid4().hex


def create_url(workspace, project):
    return f"/api/agent/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/"


def item_url(workspace, ref):
    return f"/api/agent/v1/workspaces/{workspace.slug}/work-items/{ref}/"


def comments_url(workspace, ref):
    return f"{item_url(workspace, ref)}comments/"


def post(client, url, body, idempotency_key="auto", **extra):
    headers = (
        {}
        if idempotency_key is None
        else {"HTTP_IDEMPOTENCY_KEY": key() if idempotency_key == "auto" else idempotency_key}
    )
    return client.post(url, body, format="json", **headers, **extra)


class TestWhatAnAppMayDoWithoutAWriteScope:
    @pytest.fixture
    def reader(self, app, person):
        return client_with(app, person, "profile time:read work_items:read")

    def test_every_write_is_refused_and_names_the_scope(self, reader, workspace, project, person):
        make_issue(project, "Task", assignees=[person])
        calls = [
            ("post", create_url(workspace, project), {"name": "x"}, "work_items:write"),
            ("patch", item_url(workspace, "PRJ-1"), {"priority": "high"}, "work_items:write"),
            ("post", comments_url(workspace, "PRJ-1"), {"text": "hi"}, "work_items:write"),
            (
                "post",
                "/api/agent/v1/me/timer/start/",
                {"workspace": workspace.slug, "work_item": "PRJ-1"},
                "time:write",
            ),
            ("post", "/api/agent/v1/me/timer/stop/", {}, "time:write"),
            (
                "post",
                "/api/agent/v1/me/time-entries/",
                {"workspace": "a", "work_item": "B-1", "minutes": 5},
                "time:write",
            ),
        ]
        for method, url, body, scope in calls:
            response = getattr(reader, method)(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key())
            assert response.status_code == 403, url
            assert response.json()["error"] == "insufficient_scope" and response.json()["scope"] == scope, url

    def test_reading_still_works_on_a_path_that_can_also_write(self, reader, workspace, project):
        make_issue(project, "Task")
        assert reader.get(item_url(workspace, "PRJ-1")).status_code == 200

    def test_an_app_registered_for_reading_cannot_ask_for_more(self, make_app):
        from plane.agent.scopes import READ_ONLY_SCOPES

        reader = make_app(allowed_scopes=READ_ONLY_SCOPES)
        response, _ = reader.link_request(scope="profile work_items:write")
        assert response.status_code == 400 and response.json()["error"] == "invalid_scope"

    def test_a_session_cannot_use_them(self, app, person, workspace, project):
        response = app.browser(person).post(create_url(workspace, project), {"name": "x"}, format="json")
        assert response.status_code == 401

    def test_only_json_is_taken(self, client, workspace, project):
        response = client.post(create_url(workspace, project), {"name": "x"}, HTTP_IDEMPOTENCY_KEY=key())
        assert response.status_code == 415


class TestCreatingAWorkItem:
    def test_a_work_item_is_created_as_the_person_and_described_back(
        self, client, workspace, project, person, colleague
    ):
        label = make_label(project)
        response = post(
            client,
            create_url(workspace, project),
            {
                "name": "Fix the header",
                "description": "The logo overlaps the menu.\n\nSee the Figma frame.",
                "priority": "high",
                "assignees": [str(colleague.id)],
                "labels": [str(label.id)],
                "start_date": "2026-03-02",
                "target_date": "2026-03-10",
            },
        )
        assert response.status_code == 201, response.content
        body = response.json()
        assert body["ref"] == "PRJ-1" and body["priority"] == "high" and body["target_date"] == "2026-03-10"
        assert body["description"] == "The logo overlaps the menu.\nSee the Figma frame."
        assert [person_["id"] for person_ in body["assignees"]] == [str(colleague.id)] and body["labels"] == ["bug"]
        assert body["state"]["name"] == "Backlog"
        issue = Issue.objects.get()
        assert issue.created_by == person, "it is the person's work item, not the app's"
        assert body["url"].endswith(f"/{workspace.slug}/browse/PRJ-1/")

    def test_the_activity_and_webhook_pipelines_are_told_as_for_a_web_app_create(
        self, client, workspace, project, colleague, background_tasks, person
    ):
        post(client, create_url(workspace, project), {"name": "Task", "assignees": [str(colleague.id)]})
        activity = background_tasks.issue_activity.call_args.kwargs
        assert activity["type"] == "issue.activity.created" and activity["actor_id"] == str(person.id)
        assert activity["notification"] is True and str(colleague.id) in activity["requested_data"]
        assert background_tasks.model_activity.call_args.kwargs["model_name"] == "issue"

    def test_what_a_model_writes_is_text_never_markup(self, client, workspace, project):
        post(
            client,
            create_url(workspace, project),
            {"name": "T", "description": "<script>alert(1)</script> & <b>bold</b>"},
        )
        html = Issue.objects.get().description_html
        assert "<script>" not in html and "<b>" not in html
        assert "&lt;script&gt;" in html and "&amp;" in html

    @pytest.mark.parametrize(
        "extra",
        [
            {"created_by": "someone"},
            {"is_draft": True},
            {"description_html": "<p>raw</p>"},
            {"description_binary": "AAAA"},
            {"workspace": "x"},
            {"external_id": "1", "external_source": "x"},
            {"sort_order": 1},
        ],
    )
    def test_fields_the_app_was_never_meant_to_set_are_refused(self, client, workspace, project, extra):
        response = post(client, create_url(workspace, project), {"name": "T", **extra})
        assert response.status_code == 400 and "Unknown field" in response.json()["error_description"]
        assert Issue.objects.count() == 0

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"name": ""},
            {"name": "   "},
            {"name": 5},
            {"name": "x" * 256},
            {"name": "T", "priority": "asap"},
            {"name": "T", "assignees": "everyone"},
            {"name": "T", "assignees": ["not-an-id"]},
            {"name": "T", "start_date": "tomorrow"},
            {"name": "T", "description": "x" * 20001},
            {"name": "T", "start_date": "2026-03-10", "target_date": "2026-03-02"},
        ],
    )
    def test_bad_input_is_refused_with_a_reason(self, client, workspace, project, body):
        response = post(client, create_url(workspace, project), body)
        assert response.status_code == 400 and response.json()["error"] == "invalid_request"
        assert Issue.objects.count() == 0

    def test_a_body_that_is_not_an_object_is_refused(self, client, workspace, project):
        assert post(client, create_url(workspace, project), ["name"]).status_code == 400

    def test_only_people_who_can_take_the_work_can_be_assigned(self, client, workspace, project, person):
        stranger = make_user()
        guest = make_user()
        join(workspace, guest)
        from plane.db.models import ProjectMember

        ProjectMember.objects.create(project=project, member=guest, workspace=workspace, role=GUEST)
        for wanted in (stranger, guest):
            response = post(client, create_url(workspace, project), {"name": "T", "assignees": [str(wanted.id)]})
            assert response.status_code == 400, wanted
        assert Issue.objects.count() == 0

    def test_labels_and_states_of_another_project_are_refused(self, client, workspace, project, person):
        other = make_project(workspace, "OTH", members=[(person, MEMBER)])
        foreign_label, foreign_state = make_label(other), make_state(other, "started")
        assert (
            post(client, create_url(workspace, project), {"name": "T", "labels": [str(foreign_label.id)]}).status_code
            == 400
        )
        assert (
            post(client, create_url(workspace, project), {"name": "T", "state": str(foreign_state.id)}).status_code
            == 400
        )

    def test_a_chosen_state_is_used(self, client, workspace, project):
        doing = make_state(project, "started", "Doing")
        body = post(client, create_url(workspace, project), {"name": "T", "state": str(doing.id)}).json()
        assert body["state"] == {"id": str(doing.id), "name": "Doing", "group": "started"}

    def test_a_guest_cannot_create_and_a_stranger_is_told_nothing(self, app, workspace, colleague):
        guest_person = make_user()
        join(workspace, guest_person)
        shared = make_project(workspace, "GST", members=[(guest_person, GUEST), (colleague, MEMBER)])
        as_guest = client_with(app, guest_person, WRITE)
        assert post(as_guest, create_url(workspace, shared), {"name": "T"}).status_code == 403

        private = make_project(workspace, "SEC", members=[(colleague, MEMBER)])
        missing = post(
            as_guest, f"/api/agent/v1/workspaces/{workspace.slug}/projects/{uuid.uuid4()}/work-items/", {"name": "T"}
        )
        hidden = post(as_guest, create_url(workspace, private), {"name": "T"})
        assert hidden.status_code == missing.status_code == 404 and hidden.json() == missing.json()

    def test_nothing_is_created_in_an_archived_project_or_one_the_person_has_left(
        self, client, workspace, project, person
    ):
        from django.utils import timezone

        from plane.db.models import ProjectMember

        ProjectMember.objects.filter(project=project, member=person).update(is_active=False)
        assert post(client, create_url(workspace, project), {"name": "T"}).status_code == 404
        ProjectMember.objects.filter(project=project, member=person).update(is_active=True)
        project.archived_at = timezone.now()
        project.save()
        assert post(client, create_url(workspace, project), {"name": "T"}).status_code == 404

    def test_a_project_id_that_is_not_an_id_is_refused(self, client, workspace):
        response = post(client, f"/api/agent/v1/workspaces/{workspace.slug}/projects/nope/work-items/", {"name": "T"})
        assert response.status_code == 400


class TestDoingItOnce:
    def test_a_key_is_required(self, client, workspace, project):
        response = post(client, create_url(workspace, project), {"name": "T"}, idempotency_key=None)
        assert response.status_code == 400 and "Idempotency-Key" in response.json()["error_description"]

    @pytest.mark.parametrize("bad", ["short", "has space in it", "x" * 129, "ключ-ключ-ключ"])
    def test_a_malformed_key_is_refused(self, client, workspace, project, bad):
        assert post(client, create_url(workspace, project), {"name": "T"}, idempotency_key=bad).status_code == 400

    def test_repeating_a_request_gives_the_first_answer_and_does_nothing_more(self, client, workspace, project):
        first = post(client, create_url(workspace, project), {"name": "Once"}, idempotency_key="the-one-key-1")
        again = post(client, create_url(workspace, project), {"name": "Once"}, idempotency_key="the-one-key-1")
        assert first.status_code == again.status_code == 201
        assert again.json() == first.json() and again["Idempotent-Replay"] == "true"
        assert "Idempotent-Replay" not in first
        assert Issue.objects.count() == 1

    def test_the_same_key_for_a_different_request_is_refused_not_answered_wrongly(self, client, workspace, project):
        post(client, create_url(workspace, project), {"name": "One"}, idempotency_key="the-one-key-2")
        other = post(client, create_url(workspace, project), {"name": "Two"}, idempotency_key="the-one-key-2")
        assert other.status_code == 422 and other.json()["error"] == "idempotency_key_reused"
        assert Issue.objects.count() == 1

    def test_a_refused_request_does_not_use_up_its_key(self, client, workspace, project):
        refused = post(client, create_url(workspace, project), {"name": ""}, idempotency_key="the-one-key-3")
        fixed = post(client, create_url(workspace, project), {"name": "Fixed"}, idempotency_key="the-one-key-3")
        assert refused.status_code == 400 and fixed.status_code == 201
        assert Issue.objects.count() == 1

    def test_a_request_still_being_worked_on_is_told_to_wait(self, client, workspace, project, person):
        from django.utils import timezone

        from plane.agent.models import AgentGrant
        from plane.agent.services import idempotency
        from plane.agent.tokens import hash_secret

        grant = AgentGrant.objects.get()
        body = {"name": "Slow"}
        digest = idempotency.fingerprint("POST", create_url(workspace, project), body, str(project.id))
        AgentIdempotencyKey.objects.create(
            grant=grant,
            key_hash=hash_secret("the-one-key-4"),
            request_hash=digest,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        response = post(client, create_url(workspace, project), body, idempotency_key="the-one-key-4")
        assert response.status_code == 409 and response.json()["error"] == "request_in_progress"
        assert Issue.objects.count() == 0

    def test_an_old_key_is_forgotten(self, client, workspace, project):
        post(client, create_url(workspace, project), {"name": "Old"}, idempotency_key="the-one-key-5")
        from django.utils import timezone

        AgentIdempotencyKey.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        post(client, create_url(workspace, project), {"name": "Old"}, idempotency_key="the-one-key-5")
        assert Issue.objects.count() == 2

    def test_keys_belong_to_one_connection(self, app, workspace, project, person):
        one = client_with(app, person, WRITE)
        other_person = make_user()
        join(workspace, other_person)
        from plane.db.models import ProjectMember

        ProjectMember.objects.create(project=project, member=other_person, workspace=workspace, role=MEMBER)
        two = client_with(app, other_person, WRITE)
        post(one, create_url(workspace, project), {"name": "A"}, idempotency_key="shared-key-1")
        reply = post(two, create_url(workspace, project), {"name": "A"}, idempotency_key="shared-key-1")
        assert reply.status_code == 201 and "Idempotent-Replay" not in reply
        assert Issue.objects.count() == 2


class TestAskingFirst:
    def test_a_dry_run_describes_the_work_item_without_creating_it(self, client, workspace, project, colleague):
        label = make_label(project)
        response = client.post(
            create_url(workspace, project) + "?dry_run=true",
            {"name": "Plan", "assignees": [str(colleague.id)], "labels": [str(label.id)], "priority": "urgent"},
            format="json",
        )
        body = response.json()
        assert response.status_code == 200 and body["dry_run"] is True and body["valid"] is True
        preview = body["would_create"]
        assert (
            preview["project"]["identifier"] == "PRJ" and preview["name"] == "Plan" and preview["priority"] == "urgent"
        )
        assert preview["assignees"] == [{"id": str(colleague.id), "display_name": colleague.display_name}]
        assert preview["labels"] == ["bug"] and preview["state"]["name"] == "Backlog"
        assert Issue.objects.count() == 0 and AgentIdempotencyKey.objects.count() == 0

    def test_a_dry_run_still_refuses_what_a_real_one_would(self, client, workspace, project):
        response = client.post(
            create_url(workspace, project) + "?dry_run=true",
            {"name": "T", "assignees": [str(uuid.uuid4())]},
            format="json",
        )
        assert response.status_code == 400

    def test_a_dry__run_of_a_change_reports_it_without_making_it(self, client, workspace, project):
        make_issue(project, "Task", priority="low")
        response = client.patch(item_url(workspace, "PRJ-1") + "?dry_run=true", {"priority": "high"}, format="json")
        assert response.json()["would_change"] == {"priority": {"from": "low", "to": "high"}}
        assert Issue.objects.get().priority == "low"


class TestChangingAWorkItem:
    def test_name_priority_state_and_dates_change_and_the_answer_says_what_changed(
        self, client, workspace, project, background_tasks
    ):
        issue = make_issue(project, "Old name", priority="low", group="backlog")
        doing = make_state(project, "started", "Doing")
        response = client.patch(
            item_url(workspace, "PRJ-1"),
            {"name": "New name", "priority": "high", "state": str(doing.id), "target_date": "2026-03-20"},
            format="json",
        )
        body = response.json()
        assert response.status_code == 200
        assert set(body["changed"]) == {"name", "priority", "state", "target_date"}
        assert body["changed"]["priority"] == {"from": "low", "to": "high"}
        assert body["work_item"]["state"]["name"] == "Doing" and body["work_item"]["name"] == "New name"
        issue.refresh_from_db()
        assert issue.state_id == doing.id and issue.target_date == date(2026, 3, 20)
        activity = background_tasks.issue_activity.call_args.kwargs
        assert activity["type"] == "issue.activity.updated" and '"state_id"' in activity["requested_data"]

    def test_moving_to_done_sets_the_completion_time(self, client, workspace, project):
        issue = make_issue(project, "Task", group="started")
        done = make_state(project, "completed", "Done")
        client.patch(item_url(workspace, "PRJ-1"), {"state": str(done.id)}, format="json")
        issue.refresh_from_db()
        assert issue.completed_at is not None

    def test_people_are_added_and_removed_never_replaced(self, client, workspace, project, person, colleague):
        make_issue(project, "Task", assignees=[person])
        added = client.patch(item_url(workspace, "PRJ-1"), {"add_assignees": [str(colleague.id)]}, format="json").json()
        assert sorted(item["id"] for item in added["work_item"]["assignees"]) == sorted(
            [str(person.id), str(colleague.id)]
        )
        removed = client.patch(
            item_url(workspace, "PRJ-1"), {"remove_assignees": [str(person.id)]}, format="json"
        ).json()
        assert [item["id"] for item in removed["work_item"]["assignees"]] == [str(colleague.id)]

    def test_somebody_who_is_not_in_the_project_cannot_be_added(self, client, workspace, project, person):
        make_issue(project, "Task")
        stranger = make_user()
        response = client.patch(item_url(workspace, "PRJ-1"), {"add_assignees": [str(stranger.id)]}, format="json")
        assert response.status_code == 400

    def test_labels_are_added_and_removed(self, client, workspace, project):
        make_issue(project, "Task")
        label = make_label(project, "urgent-fix")
        added = client.patch(item_url(workspace, "PRJ-1"), {"add_labels": [str(label.id)]}, format="json").json()
        assert added["work_item"]["labels"] == ["urgent-fix"]
        removed = client.patch(item_url(workspace, "PRJ-1"), {"remove_labels": [str(label.id)]}, format="json").json()
        assert removed["work_item"]["labels"] == []

    def test_a_date_is_cleared_by_sending_null(self, client, workspace, project):
        issue = make_issue(project, "Task", target_date=date(2026, 3, 10))
        response = client.patch(item_url(workspace, "PRJ-1"), {"target_date": None}, format="json")
        assert response.json()["changed"]["target_date"] == {"from": "2026-03-10", "to": None}
        issue.refresh_from_db()
        assert issue.target_date is None

    def test_changing_nothing_changes_nothing_and_tells_nobody(self, client, workspace, project, background_tasks):
        make_issue(project, "Task", priority="high")
        response = client.patch(item_url(workspace, "PRJ-1"), {"priority": "high"}, format="json")
        assert response.json()["changed"] == {}
        background_tasks.issue_activity.assert_not_called()
        assert not AgentAuditLog.objects.filter(event="write").exists()

    @pytest.mark.parametrize(
        "body",
        [{}, {"description": "new text"}, {"assignees": []}, {"created_by": "x"}, {"priority": "asap"}, {"name": ""}],
    )
    def test_only_the_listed_fields_and_at_least_one(self, client, workspace, project, body):
        make_issue(project, "Task")
        assert client.patch(item_url(workspace, "PRJ-1"), body, format="json").status_code == 400

    def test_a_state_of_another_project_is_refused(self, client, workspace, project, person):
        make_issue(project, "Task")
        other = make_project(workspace, "OTH", members=[(person, MEMBER)])
        foreign = make_state(other, "started")
        assert client.patch(item_url(workspace, "PRJ-1"), {"state": str(foreign.id)}, format="json").status_code == 400

    def test_a_running_timer_blocks_a_move_to_a_state_where_time_cannot_be_tracked(
        self, client, workspace, project, person
    ):
        from plane.tests.contract.agent.world import at, log_time

        issue = make_issue(project, "Task", assignees=[person], group="started")
        log_time(issue, person, 5, at=at(2026, 3, 4, 10), running=True)
        done = make_state(project, "completed", "Done")
        response = client.patch(item_url(workspace, "PRJ-1"), {"state": str(done.id)}, format="json")
        assert response.status_code == 409 and response.json()["error"] == "timer_running"
        issue.refresh_from_db()
        assert issue.state.group == "started"
        # and the same move is fine with no timer running
        IssueWorkLog.objects.all().delete(soft=False)
        assert client.patch(item_url(workspace, "PRJ-1"), {"state": str(done.id)}, format="json").status_code == 200

    def test_a_guest_cannot_change_work_even_their_own(self, app, workspace, colleague):
        guest_person = make_user()
        join(workspace, guest_person)
        shared = make_project(workspace, "GST", members=[(guest_person, GUEST), (colleague, MEMBER)])
        make_issue(shared, "Mine", author=guest_person)
        as_guest = client_with(app, guest_person, WRITE)
        assert as_guest.patch(item_url(workspace, "GST-1"), {"priority": "high"}, format="json").status_code == 403

    def test_work_the_person_cannot_see_cannot_be_changed_or_probed(self, client, workspace, colleague):
        private = make_project(workspace, "SEC", members=[(colleague, MEMBER)])
        make_issue(private, "Salaries")
        hidden = client.patch(item_url(workspace, "SEC-1"), {"priority": "low"}, format="json")
        absent = client.patch(item_url(workspace, "SEC-9"), {"priority": "low"}, format="json")
        assert hidden.status_code == absent.status_code == 404 and hidden.json() == absent.json()

    def test_a_work_item_can_be_named_by_id_even_when_the_id_ends_in_digits(self, client, workspace, project):
        wanted = uuid.UUID("12345678-1234-4234-8234-123456789012")
        make_issue(project, "Task", id=wanted)
        assert client.get(item_url(workspace, str(wanted))).json()["name"] == "Task"


class TestChangingTheDescription:
    """Adding to a description, and replacing it: what an app may do with words other people wrote."""

    RICH = '<p>First paragraph</p><ul><li>one</li></ul><image-component src="x"></image-component>'

    @pytest.fixture
    def issue(self, project):
        return make_issue(
            project,
            "Task",
            description_html="<p>First paragraph</p>",
            description_binary=b"the editor's own copy",
            description_json={"type": "doc"},
        )

    def append(self, client, workspace, text, **extra):
        return client.patch(
            item_url(workspace, "PRJ-1"),
            {"description_append": text, **extra},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key(),
        )

    def version(self, client, workspace):
        return client.get(item_url(workspace, "PRJ-1")).json()["description_version"]

    # --- adding

    def test_text_is_added_after_what_is_there_and_the_answer_says_so(self, client, workspace, issue):
        response = self.append(client, workspace, "More\n\nand more")

        body = response.json()
        assert response.status_code == 200, response.content
        assert body["changed"] == {"description": {"mode": "append", "added": "More\n\nand more"}}
        issue.refresh_from_db()
        assert issue.description_html == "<p>First paragraph</p><p>More</p><p>and more</p>"
        assert issue.description_stripped == "First paragraphMoreand more"
        assert body["work_item"]["description"] == "First paragraph\nMore\nand more"

    def test_the_editors_own_copy_is_dropped_so_the_next_editor_session_starts_from_the_text(
        self, client, workspace, issue
    ):
        self.append(client, workspace, "More")
        issue.refresh_from_db()
        assert issue.description_binary in (None, b"") and issue.description_json == {}

    def test_adding_keeps_formatting_images_and_links(self, client, workspace, project):
        issue = make_issue(project, "Rich", description_html=self.RICH)
        self.append(client, workspace, "Added")
        issue.refresh_from_db()
        assert issue.description_html == self.RICH + "<p>Added</p>"

    @pytest.mark.parametrize("empty", ["", "<p></p>", "<p><br></p>", "<p class='x'> </p>"])
    def test_adding_to_an_empty_description_makes_no_empty_paragraph_first(self, client, workspace, project, empty):
        issue = make_issue(project, "Empty", description_html=empty)
        self.append(client, workspace, "Hello")
        issue.refresh_from_db()
        assert issue.description_html == "<p>Hello</p>"

    def test_what_is_added_is_text_never_markup(self, client, workspace, issue):
        self.append(client, workspace, "<script>alert(1)</script> & <b>x</b>")
        issue.refresh_from_db()
        assert "<script>" not in issue.description_html and "<b>" not in issue.description_html
        assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;b&gt;x&lt;/b&gt;" in issue.description_html

    def test_adding_twice_with_the_same_key_adds_it_once(self, client, workspace, issue):
        same = key()
        for _ in range(2):
            response = client.patch(
                item_url(workspace, "PRJ-1"), {"description_append": "Once"}, format="json", HTTP_IDEMPOTENCY_KEY=same
            )
            assert response.status_code == 200
        issue.refresh_from_db()
        assert issue.description_html.count("Once") == 1
        assert response["Idempotent-Replay"] == "true"

    def test_adding_needs_a_key_because_doing_it_twice_is_not_harmless(self, client, workspace, issue):
        response = client.patch(item_url(workspace, "PRJ-1"), {"description_append": "x"}, format="json")
        assert response.status_code == 400
        issue.refresh_from_db()
        assert issue.description_html == "<p>First paragraph</p>"

    def test_adding_can_be_combined_with_other_changes(self, client, workspace, issue):
        response = self.append(client, workspace, "Plus", name="Renamed", priority="high")
        assert set(response.json()["changed"]) == {"name", "priority", "description"}

    def test_adding_with_the_version_just_read_works_and_with_an_old_one_is_refused(self, client, workspace, issue):
        old = self.version(client, workspace)
        assert self.append(client, workspace, "A", expected_description_version=old).status_code == 200
        stale = self.append(client, workspace, "B", expected_description_version=old)
        assert stale.status_code == 409 and stale.json()["error"] == "description_changed"
        issue.refresh_from_db()
        assert "B" not in issue.description_html

    # --- replacing

    def test_replacing_needs_the_version_that_was_read(self, client, workspace, issue):
        response = client.patch(item_url(workspace, "PRJ-1"), {"description": "New"}, format="json")
        assert response.status_code == 400
        assert "expected_description_version" in response.json()["error_description"]
        issue.refresh_from_db()
        assert issue.description_html == "<p>First paragraph</p>"

    def test_a_description_is_replaced_and_the_answer_says_from_what_to_what(self, client, workspace, issue):
        response = client.patch(
            item_url(workspace, "PRJ-1"),
            {"description": "Brand new", "expected_description_version": self.version(client, workspace)},
            format="json",
        )
        assert response.status_code == 200, response.content
        assert response.json()["changed"]["description"] == {
            "mode": "replace",
            "from": "First paragraph",
            "to": "Brand new",
            "drops_formatting": False,
        }
        issue.refresh_from_db()
        assert issue.description_html == "<p>Brand new</p>"
        assert issue.description_binary in (None, b"") and issue.description_json == {}

    def test_replacing_says_when_it_will_throw_away_formatting(self, client, workspace, project):
        make_issue(project, "Rich", description_html=self.RICH)
        response = client.patch(
            item_url(workspace, "PRJ-1") + "?dry_run=true",
            {"description": "Plain", "expected_description_version": self.version(client, workspace)},
            format="json",
        )
        assert response.json()["would_change"]["description"]["drops_formatting"] is True

    def test_a_description_changed_by_somebody_else_in_between_is_not_replaced(self, client, workspace, issue):
        read = self.version(client, workspace)
        Issue.objects.filter(pk=issue.pk).update(description_html="<p>Somebody typed this meanwhile</p>")
        response = client.patch(
            item_url(workspace, "PRJ-1"),
            {"description": "Mine", "expected_description_version": read},
            format="json",
        )
        assert response.status_code == 409 and response.json()["error"] == "description_changed"
        assert response.json()["description_version"] == description_version("<p>Somebody typed this meanwhile</p>")
        issue.refresh_from_db()
        assert issue.description_html == "<p>Somebody typed this meanwhile</p>"

    def test_replacing_with_what_is_already_there_changes_nothing(self, client, workspace, project, background_tasks):
        issue = make_issue(project, "Same", description_html="<p>Same</p>", description_binary=b"keep")
        response = client.patch(
            item_url(workspace, "PRJ-1"),
            {"description": "Same", "expected_description_version": self.version(client, workspace)},
            format="json",
        )
        assert response.json()["changed"] == {}
        issue.refresh_from_db()
        assert bytes(issue.description_binary) == b"keep"
        background_tasks.issue_activity.assert_not_called()

    # --- what is refused

    @pytest.mark.parametrize(
        "body",
        [
            {"description": "a", "description_append": "b", "expected_description_version": "0" * 16},
            {"description_append": ""},
            {"description_append": "   "},
            {"description_append": 5},
            {"description_append": "x" * 20001},
            {"description_append": "x", "expected_description_version": "short"},
            {"description_append": "x", "expected_description_version": "G" * 16},
            {"expected_description_version": "0" * 16},
            {"description": "", "expected_description_version": "0" * 16},
        ],
    )
    def test_bad_requests_are_refused_and_change_nothing(self, client, workspace, issue, body):
        response = client.patch(item_url(workspace, "PRJ-1"), body, format="json", HTTP_IDEMPOTENCY_KEY=key())
        assert response.status_code == 400, response.content
        issue.refresh_from_db()
        assert issue.description_html == "<p>First paragraph</p>"

    def test_a_description_cannot_grow_without_end(self, client, workspace, project):
        issue = make_issue(project, "Long", description_html="<p>" + "x" * 195_000 + "</p>")
        response = self.append(client, workspace, "y" * 6_000)
        assert response.status_code == 400 and "too long" in response.json()["error_description"]
        issue.refresh_from_db()
        assert len(issue.description_html) < 200_000

    def test_the_editors_binary_form_still_cannot_be_named(self, client, workspace, issue):
        response = client.patch(item_url(workspace, "PRJ-1"), {"description_binary": "AAAA"}, format="json")
        assert response.status_code == 400

    def test_a_guest_cannot_edit_a_description(self, app, workspace, colleague):
        guest = make_user()
        join(workspace, guest)
        shared = make_project(workspace, "GST", members=[(guest, GUEST), (colleague, MEMBER)])
        make_issue(shared, "Mine", author=guest, description_html="<p>x</p>")
        as_guest = client_with(app, guest, WRITE)
        response = as_guest.patch(
            item_url(workspace, "GST-1"), {"description_append": "y"}, format="json", HTTP_IDEMPOTENCY_KEY=key()
        )
        assert response.status_code == 403

    # --- asking first, and what is recorded

    def test_a_dry_run_shows_the_edit_and_changes_nothing_and_needs_no_key(self, client, workspace, issue):
        response = client.patch(
            item_url(workspace, "PRJ-1") + "?dry_run=true", {"description_append": "Later"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["would_change"] == {"description": {"mode": "append", "added": "Later"}}
        issue.refresh_from_db()
        assert issue.description_html == "<p>First paragraph</p>" and bytes(issue.description_binary)

    def test_a_dry_run_also_refuses_a_stale_version(self, client, workspace, issue):
        response = client.patch(
            item_url(workspace, "PRJ-1") + "?dry_run=true",
            {"description_append": "x", "expected_description_version": "0" * 16},
            format="json",
        )
        assert response.status_code == 409

    def test_the_activity_feed_and_webhooks_are_told_the_old_and_the_new_text(
        self, client, workspace, issue, background_tasks
    ):
        self.append(client, workspace, "More")
        activity = background_tasks.issue_activity.call_args.kwargs
        assert '"description_html": "<p>First paragraph</p><p>More</p>"' in activity["requested_data"]
        assert '"description_html": "<p>First paragraph</p>"' in activity["current_instance"]
        webhook = background_tasks.model_activity.call_args.kwargs
        assert webhook["requested_data"]["description_html"] == "<p>First paragraph</p><p>More</p>"

    def test_the_log_names_the_field_and_never_the_text(self, client, workspace, issue):
        self.append(client, workspace, "A secret plan")
        entry = AgentAuditLog.objects.get(event="write")
        assert entry.detail["fields"] == ["description"]
        assert "secret" not in str(entry.detail)

    def test_the_old_text_stays_in_the_version_history_even_when_replaced_twice_quickly(self, client, workspace, issue):
        for text in ("Second", "Third"):
            response = client.patch(
                item_url(workspace, "PRJ-1"),
                {"description": text, "expected_description_version": self.version(client, workspace)},
                format="json",
            )
            assert response.status_code == 200
        kept = [version.description_html for version in IssueDescriptionVersion.objects.filter(issue=issue)]
        assert "<p>First paragraph</p>" in kept and "<p>Second</p>" in kept and "<p>Third</p>" in kept

    def test_the_version_is_part_of_what_is_read_and_follows_the_text(self, client, workspace, issue):
        before = self.version(client, workspace)
        assert before == description_version("<p>First paragraph</p>")
        self.append(client, workspace, "More")
        assert self.version(client, workspace) != before


class TestComments:
    def test_a_comment_is_added_as_the_person(self, client, workspace, project, person, background_tasks):
        make_issue(project, "Task")
        response = post(client, comments_url(workspace, "PRJ-1"), {"text": "Looks good to me."})
        assert response.status_code == 201
        body = response.json()
        assert (
            body["text"] == "Looks good to me."
            and body["work_item"] == "PRJ-1"
            and body["author"] == person.display_name
        )
        comment = IssueComment.objects.get()
        assert comment.actor == person and comment.created_by == person
        assert background_tasks.issue_activity.call_args.kwargs["type"] == "comment.activity.created"
        shown = client.get(item_url(workspace, "PRJ-1")).json()["comments"]
        assert [item["text"] for item in shown] == ["Looks good to me."]

    def test_comment_text_is_never_markup(self, client, workspace, project):
        make_issue(project, "Task")
        post(client, comments_url(workspace, "PRJ-1"), {"text": "<img src=x onerror=alert(1)>"})
        assert "<img" not in IssueComment.objects.get().comment_html

    def test_repeating_a_comment_does_not_post_it_twice(self, client, workspace, project):
        make_issue(project, "Task")
        for _ in range(3):
            post(client, comments_url(workspace, "PRJ-1"), {"text": "Once"}, idempotency_key="comment-key-1")
        assert IssueComment.objects.count() == 1

    @pytest.mark.parametrize(
        "body", [{}, {"text": ""}, {"text": 5}, {"text": "x" * 10001}, {"text": "a", "access": "EXTERNAL"}]
    )
    def test_bad_comments_are_refused(self, client, workspace, project, body):
        make_issue(project, "Task")
        assert post(client, comments_url(workspace, "PRJ-1"), body).status_code == 400

    def test_a_guest_may_comment_on_work_they_can_see_and_not_on_anything_else(self, app, workspace, colleague):
        guest_person = make_user()
        join(workspace, guest_person)
        shared = make_project(workspace, "GST", members=[(guest_person, GUEST), (colleague, MEMBER)])
        make_issue(shared, "Theirs", author=colleague)
        make_issue(shared, "Mine", author=guest_person)
        as_guest = client_with(app, guest_person, WRITE)
        assert post(as_guest, comments_url(workspace, "GST-2"), {"text": "hi"}).status_code == 201
        assert post(as_guest, comments_url(workspace, "GST-1"), {"text": "hi"}).status_code == 404

    def test_work_nobody_can_see_cannot_be_commented_on(self, client, workspace, colleague):
        private = make_project(workspace, "SEC", members=[(colleague, MEMBER)])
        make_issue(private, "Salaries")
        assert post(client, comments_url(workspace, "SEC-1"), {"text": "hi"}).status_code == 404


class TestTheTimer:
    @pytest.fixture
    def work(self, workspace, project, person):
        return make_issue(project, "Task", assignees=[person], group="started")

    def start(self, client, workspace, ref="PRJ-1"):
        return client.post(
            "/api/agent/v1/me/timer/start/", {"workspace": workspace.slug, "work_item": ref}, format="json"
        )

    def test_starting_and_stopping_with_a_note(self, client, workspace, work, person):
        started = self.start(client, workspace)
        assert started.status_code == 201 and started.json()["started"] is True
        assert started.json()["timer"]["work_item"]["ref"] == "PRJ-1"
        assert client.get("/api/agent/v1/me/timer/").json()["running"] is True

        stopped = client.post("/api/agent/v1/me/timer/stop/", {"note": "header fix"}, format="json")
        body = stopped.json()
        assert stopped.status_code == 200 and body["stopped"] is True and body["work_item"]["ref"] == "PRJ-1"
        log = IssueWorkLog.objects.get()
        assert log.duration is not None and log.description == "header fix" and log.logged_by == person
        assert client.get("/api/agent/v1/me/timer/").json()["running"] is False

    def test_stopping_with_no_note_keeps_what_was_there_and_needs_no_body(self, client, workspace, work):
        self.start(client, workspace)
        assert client.post("/api/agent/v1/me/timer/stop/", format="json").status_code == 200

    def test_starting_again_on_the_same_work_item_changes_nothing(self, client, workspace, work):
        self.start(client, workspace)
        again = self.start(client, workspace)
        assert again.status_code == 200 and again.json()["already_running"] is True and again.json()["started"] is False
        assert IssueWorkLog.objects.count() == 1

    def test_starting_on_another_ends_the_first_and_says_so(self, client, workspace, project, work, person):
        make_issue(project, "Second", assignees=[person], group="started")
        self.start(client, workspace, "PRJ-1")
        moved = self.start(client, workspace, "PRJ-2").json()
        assert moved["started"] is True and moved["stopped_previous"]["work_item"]["ref"] == "PRJ-1"
        assert moved["timer"]["work_item"]["ref"] == "PRJ-2"
        assert IssueWorkLog.objects.filter(duration__isnull=True).count() == 1

    def test_only_an_assignee_may_start_one(self, client, workspace, project, colleague):
        make_issue(project, "Theirs", assignees=[colleague], group="started")
        response = self.start(client, workspace)
        assert response.status_code == 403 and response.json()["error"] == "not_assigned"
        assert not IssueWorkLog.objects.exists()

    def test_not_in_a_state_where_time_may_be_tracked(self, client, workspace, project, person):
        make_issue(project, "Waiting", assignees=[person], group="backlog")
        response = self.start(client, workspace)
        assert response.status_code == 409 and response.json()["error"] == "state_not_allowed"

    def test_a_guest_cannot_start_one(self, app, workspace, colleague):
        guest_person = make_user()
        join(workspace, guest_person)
        shared = make_project(workspace, "GST", members=[(guest_person, GUEST), (colleague, MEMBER)])
        make_issue(shared, "Mine", author=guest_person, assignees=[guest_person], group="started")
        as_guest = client_with(app, guest_person, WRITE)
        assert self.start(as_guest, workspace, "GST-1").status_code == 403

    def test_work_that_cannot_be_seen_cannot_have_a_timer(self, client, workspace, colleague):
        private = make_project(workspace, "SEC", members=[(colleague, MEMBER)])
        make_issue(private, "Salaries", assignees=[colleague], group="started")
        assert self.start(client, workspace, "SEC-1").status_code == 404

    def test_stopping_when_nothing_runs_is_not_found(self, client):
        response = client.post("/api/agent/v1/me/timer/stop/", {}, format="json")
        assert response.status_code == 404 and response.json()["error"] == "not_found"

    def test_a_timer_belongs_to_one_person(self, app, workspace, project, work, person, colleague):
        theirs = client_with(app, colleague, WRITE)
        assert theirs.post("/api/agent/v1/me/timer/stop/", {}, format="json").status_code == 404

    def test_unknown_fields_are_refused(self, client, workspace, work):
        response = client.post(
            "/api/agent/v1/me/timer/start/",
            {"workspace": workspace.slug, "work_item": "PRJ-1", "user": "someone-else"},
            format="json",
        )
        assert response.status_code == 400

    def test_the_web_apps_own_timer_refuses_in_the_same_words(self, workspace, project, person, colleague):
        """Both go through one set of rules; this holds the web app's side of them in place."""
        from rest_framework.test import APIClient

        issue = make_issue(project, "Theirs", assignees=[colleague], group="started")
        web = APIClient()
        web.force_authenticate(user=person)
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/timer/"
        response = web.post(url, format="json")
        assert response.status_code == 403
        assert response.json()["error"] == "Only assignees of this issue can start the timer."


class TestAddingHours:
    URL = "/api/agent/v1/me/time-entries/"

    @pytest.fixture
    def work(self, workspace, project, person):
        employ(workspace, person)
        return make_issue(project, "Task", assignees=[person], group="started")

    def add(self, client, workspace, **fields):
        idempotency_key = fields.pop("key", "auto")
        body = {"workspace": workspace.slug, "work_item": "PRJ-1", "minutes": 90, **fields}
        return post(client, self.URL, body, idempotency_key=idempotency_key)

    @freeze_time("2026-03-04 09:00:00+00:00")
    def test_hours_are_added_for_today_and_count_in_the_persons_time(self, client, workspace, work, person):
        response = self.add(client, workspace, note="header")
        assert response.status_code == 201
        body = response.json()
        assert body["date"] == "2026-03-04" and body["minutes"] == 90 and body["work_item"]["ref"] == "PRJ-1"
        entry = IssueWorkLog.objects.get()
        assert entry.duration == 5400 and entry.logged_by == person and entry.started_at is None
        assert entry.description == "header"
        summary = client.get("/api/agent/v1/me/time/?from=2026-03-04&to=2026-03-04").json()
        assert summary["total_minutes"] == 90

    @freeze_time("2026-03-04 09:00:00+00:00")
    def test_a_recent_day_can_be_named(self, client, workspace, work):
        assert self.add(client, workspace, date="2026-03-02").json()["date"] == "2026-03-02"
        summary = client.get("/api/agent/v1/me/time/?from=2026-03-02&to=2026-03-02").json()
        assert summary["total_minutes"] == 90

    @freeze_time("2026-03-04 09:00:00+00:00")
    @pytest.mark.parametrize("day", ["2026-03-05", "2026-01-01", "yesterday"])
    def test_not_the_future_and_not_long_ago(self, client, workspace, work, day):
        assert self.add(client, workspace, date=day).status_code == 400
        assert not IssueWorkLog.objects.exists()

    @pytest.mark.parametrize("minutes", [0, -5, 1441, "60", 1.5, True, None])
    def test_minutes_must_be_a_sensible_whole_number(self, client, workspace, work, minutes):
        assert self.add(client, workspace, minutes=minutes).status_code == 400

    @freeze_time("2026-03-04 09:00:00+00:00")
    def test_nothing_goes_into_a_month_that_has_been_settled(self, client, workspace, work, person):
        profile = person.hr_employment_profiles.get()
        HrPeriod.objects.create(
            workspace=workspace,
            profile=profile,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            state=HrPeriod.State.LOCKED,
            target_minutes=9000,
            actual_minutes=9000,
            balance_minutes=0,
        )
        response = self.add(client, workspace, date="2026-02-27")
        assert response.status_code == 409 and response.json()["error"] == "month_settled"
        assert response.json()["period_start"] == "2026-02-01"
        assert not IssueWorkLog.objects.exists()

    @freeze_time("2026-03-04 09:00:00+00:00")
    def test_repeating_it_does_not_add_the_hours_twice(self, client, workspace, work):
        for _ in range(3):
            self.add(client, workspace, key="hours-key-0001")
        assert IssueWorkLog.objects.count() == 1

    def test_only_work_the_person_can_change(self, client, workspace, colleague):
        private = make_project(workspace, "SEC", members=[(colleague, MEMBER)])
        make_issue(private, "Salaries")
        assert self.add(client, workspace, work_item="SEC-1").status_code == 404

    def test_the_work_item_is_named_only_with_the_work_items_scope(self, app, person, workspace, work):
        narrow = client_with(app, person, "profile time:write")
        body = self.add(narrow, workspace).json()
        assert body["work_item"] is None and body["minutes"] == 90


class TestLookups:
    def test_the_people_states_and_labels_an_app_needs_to_fill_in_a_work_item(
        self, client, workspace, project, colleague
    ):
        make_label(project, "bug")
        make_state(project, "started", "Doing")
        base = f"/api/agent/v1/workspaces/{workspace.slug}/projects/{project.id}"
        members = client.get(f"{base}/members/").json()["results"]
        assert {item["id"] for item in members} >= {str(colleague.id)}
        assert all(item["can_be_assigned"] for item in members)
        assert {item["name"] for item in client.get(f"{base}/states/").json()["results"]} >= {"Backlog", "Doing"}
        assert [item["name"] for item in client.get(f"{base}/labels/").json()["results"]] == ["bug"]

    def test_a_guest_is_listed_but_cannot_be_assigned(self, client, workspace, project):
        guest = make_user()
        join(workspace, guest)
        from plane.db.models import ProjectMember

        ProjectMember.objects.create(project=project, member=guest, workspace=workspace, role=GUEST)
        members = client.get(f"/api/agent/v1/workspaces/{workspace.slug}/projects/{project.id}/members/").json()[
            "results"
        ]
        assert next(item for item in members if item["id"] == str(guest.id))["can_be_assigned"] is False

    def test_a_project_the_person_is_not_in_is_not_described(self, client, workspace, colleague):
        private = make_project(workspace, "SEC", members=[(colleague, MEMBER)])
        base = f"/api/agent/v1/workspaces/{workspace.slug}/projects/{private.id}"
        for tail in ("members", "states", "labels"):
            assert client.get(f"{base}/{tail}/").status_code == 404

    def test_they_need_the_read_scope(self, app, person, workspace, project):
        only_write = client_with(app, person, "profile work_items:write")
        response = only_write.get(f"/api/agent/v1/workspaces/{workspace.slug}/projects/{project.id}/members/")
        assert response.status_code == 403 and response.json()["scope"] == "work_items:read"


class TestLimitsAndRecords:
    def test_writes_are_limited_harder_than_reads_and_reads_do_not_count(self, client, workspace, project, monkeypatch):
        from plane.agent.throttles import WriteRateThrottle

        monkeypatch.setattr(WriteRateThrottle, "rate", "2/minute")
        statuses = [post(client, create_url(workspace, project), {"name": f"T{n}"}).status_code for n in range(4)]
        assert statuses == [201, 201, 429, 429]
        for _ in range(5):
            assert client.get(item_url(workspace, "PRJ-1")).status_code == 200

    def test_what_was_done_is_recorded_by_id_and_never_by_content(self, client, workspace, project, person):
        post(client, create_url(workspace, project), {"name": "Secret plan", "description": "Confidential words"})
        post(client, comments_url(workspace, "PRJ-1"), {"text": "Private remark"})
        lines = list(AgentAuditLog.objects.filter(event="write").order_by("created_at"))
        assert [line.detail["action"] for line in lines] == ["work_item.create", "comment.create"]
        assert lines[0].detail["work_item"] == str(Issue.objects.get().id) and lines[0].user == person
        recorded = " ".join(str(line.detail) + line.path for line in AgentAuditLog.objects.all())
        for secret in ("Secret plan", "Confidential words", "Private remark"):
            assert secret not in recorded

    def test_old_keys_are_cleaned_up(self, client, workspace, project):
        from django.utils import timezone

        from plane.agent.tasks import purge_expired

        post(client, create_url(workspace, project), {"name": "T"})
        AgentIdempotencyKey.objects.update(expires_at=timezone.now() - timedelta(days=1))
        assert purge_expired()["idempotency_keys"] == 1


class TestTheToken:
    def test_a_token_that_was_given_up_cannot_write(self, app, person, workspace, project):
        tokens = app.link(person, scope=WRITE)
        app.revoke(tokens["refresh_token"])
        assert post(bearer(tokens["access_token"]), create_url(workspace, project), {"name": "T"}).status_code == 401
        assert Issue.objects.count() == 0

    def test_a_person_taken_out_of_the_project_cannot_keep_writing_there(self, client, workspace, project, person):
        from plane.db.models import ProjectMember

        assert post(client, create_url(workspace, project), {"name": "First"}).status_code == 201
        ProjectMember.objects.filter(project=project, member=person).update(is_active=False)
        assert post(client, create_url(workspace, project), {"name": "Second"}).status_code == 404
