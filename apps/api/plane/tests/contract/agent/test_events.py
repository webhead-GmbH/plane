# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Telling a connected app that something happened.

The things that matter: only the right person's app hears about only the right things, what it
hears holds ids and nothing a person wrote, it can tell the message is from Plane, a dead app
is not retried for ever, and an address cannot be turned into a way of reaching Plane's own
network. Nothing here sends a real request: the sender is replaced by one that records.
"""

# Python imports
import hashlib
import hmac
import json
import time
from datetime import timedelta
from types import SimpleNamespace

# Third-party imports
import pytest
import requests
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

# Module imports
from plane.agent import conf
from plane.agent.models import AgentAuditLog, AgentClient, AgentEvent, AgentGrant, AgentToken
from plane.agent.services import events
from plane.agent.tasks import purge_expired
from plane.agent.tokens import hash_secret
from plane.app.permissions import ROLE
from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import IssueActivity
from plane.tests.contract.agent.conftest import OWN_ORIGIN
from plane.tests.contract.agent.world import join, make_issue, make_project, make_state, make_user, make_workspace

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

HOOK = "https://bot.example.com/hooks/plane"
TITLE = "Quarterly figures for the Hartmann account"
SAM_NAME = "Sam Hiddenname"


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def close(self):
        pass


@pytest.fixture
def outbox(monkeypatch):
    """Stands in for the network: records what would be sent, answers with `.status` or raises `.error`."""
    sent = SimpleNamespace(calls=[], status=200, error=None)

    def fake(method, url, **kwargs):
        sent.calls.append({"method": method, "url": url, **kwargs})
        if sent.error is not None:
            raise sent.error
        return FakeResponse(sent.status)

    monkeypatch.setattr(events, "pinned_fetch", fake)
    return sent


@pytest.fixture(autouse=True)
def events_run_inline(monkeypatch):
    """Dispatch happens at once, and delivery is left to the test, which calls `events.deliver_once`."""
    from plane.agent import tasks

    queued = []
    monkeypatch.setattr(events, "transaction", SimpleNamespace(on_commit=lambda function: function()))
    monkeypatch.setattr(tasks.deliver_agent_event, "delay", lambda event_id: queued.append(event_id))
    monkeypatch.setattr(tasks.dispatch_activity_events, "delay", lambda ids: events.dispatch_activities(ids))
    return queued


@pytest.fixture
def workspace(person):
    workspace = make_workspace()
    join(workspace, person)
    return workspace


@pytest.fixture
def sam(workspace):
    user = make_user(first_name="Sam", last_name="Hiddenname", display_name=SAM_NAME)
    join(workspace, user)
    return user


@pytest.fixture
def project(workspace, person, sam):
    return make_project(workspace, "EVT", members=[(person, ROLE.MEMBER.value), (sam, ROLE.MEMBER.value)])


@pytest.fixture
def bot(app):
    """The app, with an address to be told at."""
    AgentClient.objects.filter(pk=app.client.pk).update(webhook_url=HOOK)
    app.client.refresh_from_db()
    return app


@pytest.fixture
def grant(bot, person):
    bot.link(person, scope="profile work_items:read")
    return AgentGrant.objects.get(user=person)


def change(issue, actor, requested, current=None):
    """Plane records an update to a work item, the way its own views ask the activity task to."""
    issue_activity(
        type="issue.activity.updated",
        requested_data=json.dumps(requested),
        current_instance=json.dumps(current or {}),
        issue_id=str(issue.id),
        actor_id=str(actor.id),
        project_id=str(issue.project_id),
        epoch=int(time.time()),
    )


def events_of(grant):
    return list(AgentEvent.objects.filter(grant=grant).order_by("created_at"))


class TestWhoIsToldWhat:
    def test_being_given_a_work_item_by_somebody_else(self, grant, person, sam, project):
        issue = make_issue(project, TITLE)

        change(issue, sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})

        (event,) = events_of(grant)
        assert event.event_type == "work_item.assigned"
        assert event.payload == {
            "workspace": issue.workspace.slug,
            "work_item": {"id": str(issue.id), "ref": "EVT-1", "project_id": str(project.id)},
        }

    def test_being_taken_off_one(self, grant, person, sam, project):
        issue = make_issue(project, TITLE, assignees=[person])
        change(issue, sam, {"assignee_ids": []}, {"assignee_ids": [str(person.id)]})
        assert [event.event_type for event in events_of(grant)] == ["work_item.unassigned"]

    def test_a_new_due_date_or_state_on_work_that_is_theirs(self, grant, person, sam, project):
        issue = make_issue(project, TITLE, assignees=[person])
        done = make_state(project, "completed")

        change(issue, sam, {"target_date": "2026-03-10"}, {"target_date": None})
        change(issue, sam, {"state_id": str(done.id)}, {"state_id": str(issue.state_id)})

        assert [event.event_type for event in events_of(grant)] == [
            "work_item.due_date_changed",
            "work_item.state_changed",
        ]

    def test_work_that_is_not_theirs_is_not_news(self, grant, sam, project):
        issue = make_issue(project, TITLE, assignees=[sam])
        change(issue, sam, {"target_date": "2026-03-10"}, {"target_date": None})
        assert events_of(grant) == []

    def test_what_they_did_themselves_is_not_news_to_them(self, grant, person, project):
        issue = make_issue(project, TITLE, assignees=[person])
        change(issue, person, {"target_date": "2026-03-10"}, {"target_date": None})
        change(issue, person, {"assignee_ids": []}, {"assignee_ids": [str(person.id)]})
        assert events_of(grant) == []

    def test_other_changes_say_nothing(self, grant, person, sam, project):
        issue = make_issue(project, TITLE, assignees=[person])
        change(issue, sam, {"name": "A new name"}, {"name": TITLE})
        change(issue, sam, {"priority": "urgent"}, {"priority": "low"})
        assert events_of(grant) == []

    def test_one_event_however_often_it_was_recorded_in_one_go(self, grant, person, sam, project):
        issue = make_issue(project, TITLE, assignees=[person])
        change(issue, sam, {"target_date": "2026-03-10"}, {"target_date": None})
        first = IssueActivity.objects.filter(issue=issue, field="target_date").first()
        duplicate = IssueActivity.objects.create(
            issue=issue, project=project, workspace=issue.workspace, actor=sam, verb="updated", field="target_date"
        )
        AgentEvent.objects.all().delete()

        assert events.dispatch_activities([first.id, duplicate.id]) == 1

    def test_work_the_person_can_no_longer_see_is_not_announced(self, grant, person, sam, project):
        issue = make_issue(project, TITLE, assignees=[person], archived_at=timezone.now())
        change(issue, sam, {"target_date": "2026-03-10"}, {"target_date": None})
        assert events_of(grant) == []

    def test_somebody_who_left_the_project_is_not_told_about_its_work(self, grant, person, sam, project):
        from plane.db.models import ProjectMember

        issue = make_issue(project, TITLE, assignees=[person])
        ProjectMember.objects.filter(project=project, member=person).update(is_active=False)
        change(issue, sam, {"target_date": "2026-03-10"}, {"target_date": None})
        assert events_of(grant) == []

    def test_only_the_person_whose_work_it_is(self, bot, grant, person, sam, workspace, project):
        colleague = make_user(display_name="Another Person")
        join(workspace, colleague)
        from plane.db.models import ProjectMember

        ProjectMember.objects.create(project=project, member=colleague, workspace=workspace, role=ROLE.MEMBER.value)
        bot.link(colleague, scope="profile work_items:read", account_id="777")
        issue = make_issue(project, TITLE, assignees=[person])

        change(issue, sam, {"target_date": "2026-03-10"}, {"target_date": None})

        assert [event.grant.user_id for event in AgentEvent.objects.all()] == [person.id]


class TestWhoIsNotToldAnything:
    def test_an_app_without_an_address(self, app, person, sam, project):
        app.link(person, scope="profile work_items:read")
        issue = make_issue(project, TITLE)
        change(issue, sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})
        assert AgentEvent.objects.count() == 0

    def test_an_address_that_was_switched_off(self, bot, grant, person, sam, project):
        AgentClient.objects.filter(pk=bot.client.pk).update(webhook_disabled_at=timezone.now())
        change(make_issue(project, TITLE), sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})
        assert events_of(grant) == []

    def test_a_connection_that_cannot_see_work_items(self, bot, person, sam, project):
        bot.link(person, scope="profile time:read")
        change(make_issue(project, TITLE), sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})
        assert AgentEvent.objects.count() == 0

    def test_a_connection_that_has_ended(self, grant, person, sam, project):
        AgentGrant.objects.filter(pk=grant.pk).update(revoked_at=timezone.now())
        change(make_issue(project, TITLE), sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})
        assert AgentEvent.objects.count() == 0

    def test_a_person_who_has_been_deactivated(self, grant, person, sam, project):
        type(person).objects.filter(pk=person.pk).update(is_active=False)
        change(make_issue(project, TITLE), sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})
        assert AgentEvent.objects.count() == 0

    def test_an_app_that_has_been_switched_off(self, bot, grant, person, sam, project):
        AgentClient.objects.filter(pk=bot.client.pk).update(is_active=False)
        change(make_issue(project, TITLE), sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})
        assert AgentEvent.objects.count() == 0

    def test_a_flood_is_capped_per_connection(self, grant, person, sam, project, monkeypatch):
        monkeypatch.setattr(conf, "MAX_PENDING_EVENTS", 2)
        for number in range(4):
            issue = make_issue(project, f"Task {number}", assignees=[person])
            change(issue, sam, {"target_date": "2026-03-10"}, {"target_date": None})
        assert len(events_of(grant)) == 2

    def test_a_failure_to_tell_never_stops_the_work_item_being_recorded(self, grant, person, sam, project, monkeypatch):
        def broken(activities):
            raise RuntimeError("the event system is down")

        monkeypatch.setattr(events, "announce_activities", broken)
        issue = make_issue(project, TITLE)

        change(issue, sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})

        assert IssueActivity.objects.filter(issue=issue, field="assignees").count() == 1


class TestWhatIsSent:
    def deliver(self, event):
        event.refresh_from_db()
        return events.deliver_once(AgentEvent.objects.select_related("grant", "grant__client").get(pk=event.pk))

    def make_event(self, grant, person, sam, project):
        change(make_issue(project, TITLE), sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})
        return events_of(grant)[0]

    def test_ids_and_the_kind_of_thing_and_nothing_a_person_wrote(self, outbox, grant, person, sam, project):
        event = self.make_event(grant, person, sam, project)

        assert self.deliver(event) == (events.DELIVERED, 0)

        (call,) = outbox.calls
        assert call["method"] == "POST" and call["url"] == HOOK
        body = json.loads(call["data"])
        assert body == {
            "id": str(event.id),
            "type": "work_item.assigned",
            "created_at": event.created_at.isoformat(),
            "connection": {"id": str(grant.id), "account": {"provider": "telegram", "id": "424242"}},
            "data": event.payload,
        }
        raw = call["data"].decode()
        for private in (TITLE, SAM_NAME, "Hartmann", person.display_name, person.email):
            assert private not in raw

    def test_it_can_be_told_apart_from_a_forgery(self, outbox, grant, person, sam, project):
        event = self.make_event(grant, person, sam, project)
        self.deliver(event)

        call = outbox.calls[0]
        headers = call["headers"]
        timestamp, signature = headers["X-Plane-Agent-Timestamp"], headers["X-Plane-Agent-Signature"]
        # What the app's developer is told to do, written out independently of the code under test.
        derived = hmac.new(
            settings.SECRET_KEY.encode(),
            f"plane-agent-webhook:{grant.client.id}:{grant.client.webhook_secret_version}".encode(),
            hashlib.sha256,
        ).hexdigest()
        secret = "plane_whsec_" + derived
        expected = hmac.new(secret.encode(), timestamp.encode() + b"." + call["data"], hashlib.sha256).hexdigest()
        assert signature == f"v1={expected}"
        assert abs(int(timestamp) - time.time()) < 60
        assert headers["X-Plane-Agent-Event"] == "work_item.assigned"
        assert headers["X-Plane-Agent-Delivery"] == str(event.id)
        assert headers["Content-Type"] == "application/json"

    def test_the_secret_is_not_in_the_database_and_each_app_has_its_own(self, app, make_app, bot):
        other = make_app()
        AgentClient.objects.filter(pk=other.client.pk).update(webhook_url=HOOK)
        other.client.refresh_from_db()
        assert events.webhook_secret(bot.client) != events.webhook_secret(other.client)
        assert events.webhook_secret(bot.client).startswith("plane_whsec_")
        stored = " ".join(str(value) for value in AgentClient.objects.filter(pk=bot.client.pk).values()[0].values())
        assert events.webhook_secret(bot.client) not in stored

    def test_the_same_event_keeps_its_id_and_gets_a_fresh_timestamp_when_retried(
        self, outbox, grant, person, sam, project
    ):
        event = self.make_event(grant, person, sam, project)
        outbox.status = 503
        assert self.deliver(event) == (events.RETRY, conf.WEBHOOK_RETRY_SCHEDULE[0])
        outbox.status = 200
        assert self.deliver(event)[0] == events.DELIVERED
        first, second = outbox.calls
        assert first["headers"]["X-Plane-Agent-Delivery"] == second["headers"]["X-Plane-Agent-Delivery"]
        event.refresh_from_db()
        assert event.status == "delivered" and event.attempts == 2 and event.delivered_at is not None

    def test_the_answer_is_never_read(self, outbox, grant, person, sam, project):
        event = self.make_event(grant, person, sam, project)
        self.deliver(event)
        assert outbox.calls[0]["stream"] is True
        assert "allow_redirects" not in outbox.calls[0]  # the sender never follows them, whatever is asked

    def test_what_is_sent_is_pinned_and_checked_by_planes_own_sender(self):
        from plane.utils import url_security

        assert events.pinned_fetch is url_security.pinned_fetch


class TestWhenTheAppDoesNotAnswer:
    def event(self, grant, person, sam, project):
        change(make_issue(project, TITLE), sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})
        return events_of(grant)[-1]

    def fresh(self, event):
        return AgentEvent.objects.select_related("grant", "grant__client").get(pk=event.pk)

    def test_it_waits_longer_each_time_and_then_gives_up(self, outbox, grant, person, sam, project):
        event = self.event(grant, person, sam, project)
        outbox.status = 500

        waits = []
        for _ in range(len(conf.WEBHOOK_RETRY_SCHEDULE) + 1):
            outcome, wait = events.deliver_once(self.fresh(event))
            waits.append((outcome, wait))

        assert [wait for _outcome, wait in waits[:-1]] == list(conf.WEBHOOK_RETRY_SCHEDULE)
        assert all(outcome == events.RETRY for outcome, _wait in waits[:-1]) and waits[-1][0] == events.GAVE_UP
        event.refresh_from_db()
        assert event.status == "failed" and event.attempts == len(conf.WEBHOOK_RETRY_SCHEDULE) + 1
        assert event.last_status_code == 500 and event.last_error == "http_status"
        # Once given up on, it is not tried again.
        assert events.deliver_once(self.fresh(event)) == (events.GAVE_UP, 0)
        assert len(outbox.calls) == len(conf.WEBHOOK_RETRY_SCHEDULE) + 1

    def test_no_wait_outlasts_the_brokers_consumer_timeout(self):
        """A retry waits on the worker as an unacknowledged message; RabbitMQ drops the channel of a consumer
        that holds one longer than `consumer_timeout` (30 minutes by default), taking every task on it too."""
        assert max(conf.WEBHOOK_RETRY_SCHEDULE) <= 600

    def test_a_network_failure_is_a_failed_attempt_not_a_crash(self, outbox, grant, person, sam, project):
        event = self.event(grant, person, sam, project)
        outbox.error = requests.ConnectTimeout("no answer")
        assert events.deliver_once(self.fresh(event)) == (events.RETRY, conf.WEBHOOK_RETRY_SCHEDULE[0])
        event.refresh_from_db()
        assert event.last_error == "ConnectTimeout"

    def test_a_redirect_is_a_failure_and_is_not_followed(self, outbox, grant, person, sam, project):
        event = self.event(grant, person, sam, project)
        outbox.status = 302
        assert events.deliver_once(self.fresh(event))[0] == events.RETRY
        assert len(outbox.calls) == 1

    def test_an_address_that_became_unsafe_is_refused_and_switched_off_at_once(
        self, outbox, bot, grant, person, sam, project
    ):
        event = self.event(grant, person, sam, project)
        outbox.error = ValueError("resolves to a private address")

        assert events.deliver_once(self.fresh(event)) == (events.GAVE_UP, 0)

        bot.client.refresh_from_db()
        assert bot.client.webhook_disabled_at is not None
        assert AgentAuditLog.objects.filter(event="webhook_disabled", detail__reason="address_refused").exists()
        event.refresh_from_db()
        assert event.status == "failed" and event.last_error == "address_refused"

    def test_an_app_that_keeps_failing_is_switched_off_and_not_retried_for_ever(
        self, outbox, bot, grant, person, sam, project, monkeypatch
    ):
        monkeypatch.setattr(conf, "WEBHOOK_FAILURE_LIMIT", 3)
        outbox.status = 500
        for number in range(3):
            event = self.event(grant, person, sam, project)
            for _ in range(len(conf.WEBHOOK_RETRY_SCHEDULE) + 1):
                events.deliver_once(self.fresh(event))
            bot.client.refresh_from_db()
            assert bot.client.webhook_failures == number + 1

        assert bot.client.webhook_disabled_at is not None
        assert AgentAuditLog.objects.filter(event="webhook_disabled", detail__reason="failures").exists()
        before = AgentEvent.objects.count()
        change(make_issue(project, "Another"), sam, {"assignee_ids": [str(person.id)]}, {"assignee_ids": []})
        assert AgentEvent.objects.count() == before

    def test_one_answer_clears_the_count(self, outbox, bot, grant, person, sam, project):
        AgentClient.objects.filter(pk=bot.client.pk).update(webhook_failures=4)
        event = self.event(grant, person, sam, project)
        assert events.deliver_once(self.fresh(event))[0] == events.DELIVERED
        bot.client.refresh_from_db()
        assert bot.client.webhook_failures == 0

    def test_work_news_is_not_sent_for_a_connection_that_ended_meanwhile(self, outbox, grant, person, sam, project):
        event = self.event(grant, person, sam, project)
        AgentGrant.objects.filter(pk=grant.pk).update(revoked_at=timezone.now())

        assert events.deliver_once(self.fresh(event)) == (events.GAVE_UP, 0)

        assert outbox.calls == []
        event.refresh_from_db()
        assert event.status == "failed" and event.last_error == "connection_ended"

    def test_work_news_is_not_sent_about_a_person_deactivated_meanwhile(self, outbox, grant, person, sam, project):
        event = self.event(grant, person, sam, project)
        type(person).objects.filter(pk=person.pk).update(is_active=False)

        assert events.deliver_once(self.fresh(event)) == (events.GAVE_UP, 0)

        assert outbox.calls == []

    def test_nothing_is_sent_once_the_address_is_gone(self, outbox, bot, grant, person, sam, project):
        event = self.event(grant, person, sam, project)
        AgentClient.objects.filter(pk=bot.client.pk).update(webhook_url="")
        assert events.deliver_once(self.fresh(event)) == (events.GAVE_UP, 0)
        assert outbox.calls == []


class TestWhenAConnectionEnds:
    def only(self, grant):
        (event,) = events_of(grant)
        return event

    def test_the_person_ending_it_is_announced_so_the_app_can_forget_the_tokens(self, bot, grant, person, outbox):
        browser = bot.browser(person)
        assert browser.delete(f"/api/agent/connections/{grant.id}/", HTTP_ORIGIN=OWN_ORIGIN).status_code == 204

        event = self.only(grant)
        assert (event.event_type, event.payload) == ("connection.revoked", {"reason": "user"})
        # It is sent although the connection is over: that it ended is the news.
        event = AgentEvent.objects.select_related("grant", "grant__client").get(pk=event.pk)
        assert events.deliver_once(event)[0] == events.DELIVERED

    def test_an_administrator_ending_it(self, bot, grant):
        call_command("agent_client", "revoke-grants", bot.client.client_id)
        assert self.only(grant).payload == {"reason": "admin"}

    def test_a_replayed_token_is_a_security_ending(self, bot, grant, person, monkeypatch):
        tokens = bot.link(person, scope="profile work_items:read", account_id="999")
        new_grant = AgentGrant.objects.get(user=person, account_id="999")
        bot.refresh(tokens["refresh_token"])
        AgentToken.objects.filter(token_hash=hash_secret(tokens["refresh_token"])).update(
            used_at=timezone.now() - timedelta(minutes=5)
        )
        bot.refresh(tokens["refresh_token"])
        assert self.only(new_grant).payload == {"reason": "security"}

    def test_the_app_ending_it_itself_is_not_news_to_it(self, bot, grant, person):
        tokens = bot.link(person, scope="profile work_items:read", account_id="888")
        mine = AgentGrant.objects.get(user=person, account_id="888")
        assert bot.revoke(tokens["refresh_token"]).status_code == 200
        assert events_of(mine) == []

    def test_linking_the_same_account_again_is_not_an_ending_to_announce(self, bot, grant, person):
        bot.link(person, scope="profile work_items:read")
        assert events_of(grant) == []

    def test_an_ending_is_only_announced_once(self, bot, grant):
        from plane.agent import oauth

        oauth.revoke_grant(grant, oauth.BY_ADMIN)
        grant.refresh_from_db()
        oauth.revoke_grant(grant, oauth.BY_ADMIN)
        assert len(events_of(grant)) == 1

    def test_an_app_without_an_address_is_not_told(self, app, person):
        app.link(person, scope="profile work_items:read")
        call_command("agent_client", "revoke-grants", app.client.client_id)
        assert AgentEvent.objects.count() == 0

    def test_a_failure_to_announce_does_not_stop_the_connection_ending(self, bot, grant, monkeypatch):
        from plane.agent import oauth

        def broken(grant, reason):
            raise RuntimeError("down")

        monkeypatch.setattr(events, "announce_revoked", broken)
        oauth.revoke_grant(grant, oauth.BY_ADMIN)
        grant.refresh_from_db()
        assert grant.revoked_at is not None


class TestWhereAnAppIsTold:
    def test_an_address_must_be_https_unless_the_operator_trusts_the_host(self, monkeypatch):
        monkeypatch.setattr(events, "validate_url", lambda *args, **kwargs: None)
        assert events.check_webhook_url("https://bot.example.com/hook") == "https://bot.example.com/hook"
        with pytest.raises(ValueError):
            events.check_webhook_url("http://bot.example.com/hook")
        monkeypatch.setattr(settings, "WEBHOOK_ALLOWED_HOSTS", ["bot-internal"])
        assert events.check_webhook_url("http://bot-internal:8080/hook")

    @pytest.mark.parametrize(
        "address",
        [
            "ftp://bot.example.com/hook",
            "https://user:secret@bot.example.com/hook",
            "https://bot.example.com/hook#fragment",
            "https:///hook",
            "not an address",
            "",
        ],
    )
    def test_malformed_addresses_are_refused(self, address, monkeypatch):
        monkeypatch.setattr(events, "validate_url", lambda *args, **kwargs: None)
        with pytest.raises(ValueError):
            events.check_webhook_url(address)

    @pytest.mark.parametrize(
        "address",
        [
            "https://127.0.0.1/hook",
            "https://10.1.2.3/hook",
            "https://192.168.0.5/hook",
            "https://169.254.169.254/latest/meta-data/",
            "https://[::1]/hook",
        ],
    )
    def test_addresses_inside_the_network_are_refused_unless_the_operator_allows_them(self, address):
        with pytest.raises(ValueError):
            events.check_webhook_url(address)

    def test_the_command_sets_it_and_shows_the_secret_once_asked(self, bot, monkeypatch, capsys):
        monkeypatch.setattr(events, "validate_url", lambda *args, **kwargs: None)
        AgentClient.objects.filter(pk=bot.client.pk).update(webhook_url="", webhook_failures=5)

        call_command("agent_client", "webhook", bot.client.client_id, "--url", "https://bot.example.com/other")

        bot.client.refresh_from_db()
        assert bot.client.webhook_url == "https://bot.example.com/other" and bot.client.webhook_failures == 0
        out = capsys.readouterr().out
        assert events.webhook_secret(bot.client) in out

        call_command("agent_client", "webhook", bot.client.client_id, "--show-secret")
        assert events.webhook_secret(bot.client) in capsys.readouterr().out

    def test_a_new_secret_replaces_the_old_one(self, bot, capsys):
        before = events.webhook_secret(bot.client)
        call_command("agent_client", "webhook", bot.client.client_id, "--new-secret")
        bot.client.refresh_from_db()
        assert events.webhook_secret(bot.client) != before
        assert events.webhook_secret(bot.client) in capsys.readouterr().out

    def test_the_command_refuses_an_unsafe_address_and_changes_nothing(self, bot):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command("agent_client", "webhook", bot.client.client_id, "--url", "https://127.0.0.1/hook")
        bot.client.refresh_from_db()
        assert bot.client.webhook_url == HOOK

    def test_off_means_off_and_setting_an_address_again_switches_a_dead_one_back_on(self, bot, monkeypatch):
        monkeypatch.setattr(events, "validate_url", lambda *args, **kwargs: None)
        AgentClient.objects.filter(pk=bot.client.pk).update(webhook_disabled_at=timezone.now(), webhook_failures=10)

        call_command("agent_client", "webhook", bot.client.client_id, "--url", HOOK)
        bot.client.refresh_from_db()
        assert bot.client.webhook_disabled_at is None and bot.client.webhook_failures == 0

        call_command("agent_client", "webhook", bot.client.client_id, "--off")
        bot.client.refresh_from_db()
        assert bot.client.webhook_url == ""

    def test_the_app_cannot_set_its_own_address(self, bot, person):
        tokens = bot.link(person, scope="profile work_items:read")
        from plane.tests.contract.agent.conftest import bearer

        client = bearer(tokens["access_token"])
        for method in (client.post, client.put, client.patch):
            assert method(
                "/api/agent/v1/oauth/requests/", {"webhook_url": "https://evil.example/"}, format="json"
            ).status_code in (
                401,
                403,
                405,
            )
        bot.client.refresh_from_db()
        assert bot.client.webhook_url == HOOK


class TestHousekeeping:
    def test_old_events_are_purged_whatever_their_state(self, grant):
        old = timezone.now() - conf.EVENT_RETENTION - timedelta(hours=1)
        for status in ("pending", "delivered", "failed"):
            AgentEvent.objects.create(grant=grant, event_type="work_item.assigned", status=status, created_at=old)
        recent = AgentEvent.objects.create(grant=grant, event_type="work_item.assigned")

        assert purge_expired()["events"] == 3
        assert list(AgentEvent.objects.all()) == [recent]

    def test_events_go_with_their_connection(self, grant):
        AgentEvent.objects.create(grant=grant, event_type="work_item.assigned")
        AgentGrant.objects.filter(pk=grant.pk).delete()
        assert AgentEvent.objects.count() == 0

    def test_the_listing_shows_where_each_app_is_told(self, bot, capsys):
        call_command("agent_client", "list")
        assert HOOK in capsys.readouterr().out
