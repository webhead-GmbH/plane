# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The instance administrators' screen for connected apps.

What matters here: only an instance administrator, through the admin app's own session, can
register or change an app; a secret is shown when it is made and never again (and never
stored); the screen follows the same rules as the `agent_client` command; and everything an
administrator does leaves a line in the audit log that names what was done and never a secret.
"""

# Python imports
from types import SimpleNamespace
from uuid import uuid4

# Third-party imports
import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

# Module imports
from plane.agent.models import AgentAuditLog, AgentClient, AgentGrant
from plane.agent.scopes import DEFAULT_SCOPES, SCOPES
from plane.agent.services import events
from plane.agent.tokens import hash_secret
from plane.license.models import Instance, InstanceAdmin
from plane.tests.contract.agent.conftest import OWN_ORIGIN, REDIRECT_URI
from plane.tests.contract.agent.world import make_user

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

APPS = "/api/instances/agent-apps/"
HOOK = "https://bot.example.com/hooks/plane"


def url(client_id, *tail):
    return APPS + client_id + "/" + "".join(part + "/" for part in tail)


def signed_in(user):
    """A browser signed in to the *admin* app: that app keeps its own session cookie."""
    browser = APIClient()
    browser.force_login(user)
    browser.cookies[settings.ADMIN_SESSION_COOKIE_NAME] = browser.cookies[settings.SESSION_COOKIE_NAME].value
    return browser


@pytest.fixture
def instance():
    return Instance.objects.first() or Instance.objects.create(
        instance_name="test", instance_id=uuid4().hex, current_version="1.0.0", last_checked_at=timezone.now()
    )


@pytest.fixture
def admin(instance):
    user = make_user()
    InstanceAdmin.objects.create(instance=instance, user=user, role=20)
    return signed_in(user)


@pytest.fixture
def bot(make_app):
    return make_app(name="Telegram bot", allowed_scopes=list(DEFAULT_SCOPES), webhook_url=HOOK)


def register(admin, **overrides):
    body = {"name": "Telegram bot", "redirect_uris": [REDIRECT_URI]}
    body.update(overrides)
    return admin.post(APPS, body, format="json", HTTP_ORIGIN=OWN_ORIGIN)


class TestWhoMayUseIt:
    def test_it_is_for_instance_administrators(self, instance, bot):
        ordinary = signed_in(make_user())
        assert ordinary.get(APPS).status_code == 403
        assert register(ordinary).status_code == 403
        assert AgentClient.objects.filter(name="Telegram bot").count() == 1  # only the fixture's

    def test_a_signed_out_browser_is_refused(self, bot):
        assert APIClient().get(APPS).status_code in (401, 403)

    def test_the_ordinary_session_is_not_the_admin_session(self, instance):
        # Signed in to Plane as an administrator in the people's own app is not being signed in to the admin app.
        user = make_user()
        InstanceAdmin.objects.create(instance=instance, user=user, role=20)
        browser = APIClient()
        browser.force_login(user)
        assert browser.get(APPS).status_code in (401, 403)

    def test_a_connected_apps_token_is_not_an_administrator(self, instance, bot, person):
        tokens = bot.link(person, scope="profile")
        from plane.tests.contract.agent.conftest import bearer

        assert bearer(tokens["access_token"]).get(APPS).status_code in (401, 403)

    def test_changes_must_come_from_plane_s_own_apps(self, admin):
        response = admin.post(
            APPS,
            {"name": "x", "redirect_uris": [REDIRECT_URI]},
            format="json",
            HTTP_ORIGIN="https://evil.example",
        )
        assert response.status_code == 403
        assert AgentClient.objects.count() == 0

    def test_nothing_is_cached(self, admin):
        assert admin.get(APPS)["Cache-Control"] == "no-store"


class TestList:
    def test_it_lists_the_apps_and_what_can_be_asked_for(self, admin, bot, person):
        bot.link(person, scope="profile")
        body = admin.get(APPS).json()

        (app,) = body["apps"]
        assert app["client_id"] == bot.client.client_id
        assert app["name"] == "Telegram bot"
        assert app["connections"] == 1
        assert app["webhook"] == {"url": HOOK, "state": "on", "failures": 0, "disabled_at": None}
        assert [scope["id"] for scope in body["scopes"]] == list(SCOPES)
        assert body["default_scopes"] == DEFAULT_SCOPES
        # What the screen needs to warn about, taken from the same place the consent screen takes it.
        team = next(scope for scope in body["scopes"] if scope["id"] == "team:read")
        assert team["others"] is True
        assert next(scope for scope in body["scopes"] if scope["id"] == "work_items:write")["writes"] is True

    def test_it_never_carries_a_secret(self, admin, bot):
        raw = admin.get(APPS).content.decode()
        assert bot.secret not in raw and hash_secret(bot.secret) not in raw
        assert events.webhook_secret(bot.client) not in raw

    def test_ended_connections_are_not_counted(self, admin, bot, person):
        bot.link(person, scope="profile")
        AgentGrant.objects.update(revoked_at=timezone.now())
        assert admin.get(APPS).json()["apps"][0]["connections"] == 0


class TestRegistering:
    def test_it_makes_the_app_and_shows_the_secret_once(self, admin):
        response = register(admin, description="Reminders")

        assert response.status_code == 201
        body = response.json()
        client = AgentClient.objects.get(client_id=body["app"]["client_id"])
        assert body["client_secret"].startswith("plane_cs_")
        # Only the hash is kept, and it is the hash of exactly what was shown.
        assert client.secret_hash == hash_secret(body["client_secret"])
        assert body["client_secret"] not in AgentClient.objects.values_list("secret_hash", flat=True)
        assert client.redirect_uris == [REDIRECT_URI] and client.description == "Reminders"
        # The secret is not in the app's own record, so listing it again cannot show it.
        assert "client_secret" not in admin.get(url(client.client_id)).json()
        assert body["client_secret"] not in admin.get(APPS).content.decode()

    def test_what_nobody_names_is_what_only_reads_the_linking_persons_own_information(self, admin):
        client = AgentClient.objects.get(client_id=register(admin).json()["app"]["client_id"])
        assert client.allowed_scopes == DEFAULT_SCOPES
        assert not any(SCOPES[scope].writes or SCOPES[scope].others for scope in client.allowed_scopes)

    def test_writing_or_seeing_colleagues_is_asked_for_by_name(self, admin):
        scopes = ["profile", "work_items:write", "team:read"]
        client = AgentClient.objects.get(client_id=register(admin, allowed_scopes=scopes).json()["app"]["client_id"])
        assert client.allowed_scopes == scopes

    def test_the_app_starts_with_no_events_address(self, admin):
        app = register(admin).json()["app"]
        assert app["is_active"] is True and app["webhook"]["state"] == "off" and app["connections"] == 0

    @pytest.mark.parametrize(
        "overrides",
        [
            {"name": ""},
            {"name": "   "},
            {"name": None},
            {"name": "x" * 121},
            {"redirect_uris": []},
            {"redirect_uris": None},
            {"redirect_uris": "https://bot.example.com/callback"},
            {"redirect_uris": ["http://bot.example.com/callback"]},
            {"redirect_uris": ["https://bot.example.com/callback#fragment"]},
            {"redirect_uris": ["https://user:pass@bot.example.com/callback"]},
            {"redirect_uris": ["javascript:alert(1)"]},
            {"redirect_uris": ["https://bot.example.com/" + "a" * 2100]},
            {"redirect_uris": [f"https://bot.example.com/{n}" for n in range(11)]},
            {"allowed_scopes": ["everything"]},
            {"allowed_scopes": "profile"},
            {"description": "d" * 1001},
        ],
    )
    def test_what_is_wrong_is_refused_in_words_and_nothing_is_made(self, admin, overrides):
        response = register(admin, **overrides)
        assert response.status_code == 400
        assert response.json()["error"]
        assert AgentClient.objects.count() == 0

    def test_plain_http_is_only_for_the_developers_own_computer(self, admin):
        assert register(admin, redirect_uris=["http://localhost:8080/cb"]).status_code == 201

    def test_it_is_written_down_without_the_secret(self, admin):
        body = register(admin).json()
        (line,) = AgentAuditLog.objects.filter(event="app_registered")
        assert line.client.client_id == body["app"]["client_id"] and line.user is not None
        assert body["client_secret"] not in str(line.detail) and body["client_secret"] not in line.path


class TestChanging:
    def test_name_description_addresses_and_scopes_can_be_changed(self, admin, bot):
        response = admin.patch(
            url(bot.client.client_id),
            {
                "name": "Webbie",
                "description": "Reminders",
                "redirect_uris": [REDIRECT_URI, "https://bot.example.com/other"],
                "allowed_scopes": ["profile", "time:read"],
            },
            format="json",
            HTTP_ORIGIN=OWN_ORIGIN,
        )

        assert response.status_code == 200
        bot.client.refresh_from_db()
        assert bot.client.name == "Webbie" and bot.client.description == "Reminders"
        assert bot.client.redirect_uris == [REDIRECT_URI, "https://bot.example.com/other"]
        assert bot.client.allowed_scopes == ["profile", "time:read"]
        assert response.json()["name"] == "Webbie"

    def test_what_is_not_named_is_left_alone(self, admin, bot):
        admin.patch(url(bot.client.client_id), {"name": "Webbie"}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        bot.client.refresh_from_db()
        assert bot.client.redirect_uris == [REDIRECT_URI] and bot.client.allowed_scopes == list(DEFAULT_SCOPES)
        assert bot.client.webhook_url == HOOK

    def test_an_app_cannot_be_left_with_nowhere_to_send_people(self, admin, bot):
        response = admin.patch(url(bot.client.client_id), {"redirect_uris": []}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        assert response.status_code == 400
        bot.client.refresh_from_db()
        assert bot.client.redirect_uris == [REDIRECT_URI]

    def test_a_bad_change_changes_nothing_at_all(self, admin, bot):
        response = admin.patch(
            url(bot.client.client_id),
            {"name": "Webbie", "allowed_scopes": ["everything"]},
            format="json",
            HTTP_ORIGIN=OWN_ORIGIN,
        )
        assert response.status_code == 400
        bot.client.refresh_from_db()
        assert bot.client.name == "Telegram bot"

    def test_switching_an_app_off_stops_its_tokens(self, admin, bot, person):
        tokens = bot.link(person, scope="profile")
        from plane.tests.contract.agent.conftest import bearer

        assert bearer(tokens["access_token"]).get("/api/agent/v1/me/").status_code == 200
        admin.patch(url(bot.client.client_id), {"is_active": False}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        assert bearer(tokens["access_token"]).get("/api/agent/v1/me/").status_code in (401, 403)

        admin.patch(url(bot.client.client_id), {"is_active": True}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        assert bearer(tokens["access_token"]).get("/api/agent/v1/me/").status_code == 200

    def test_narrowing_what_an_app_may_ask_for_does_not_reach_into_existing_connections(self, admin, bot, person):
        bot.link(person, scope="profile time:read")
        admin.patch(url(bot.client.client_id), {"allowed_scopes": ["profile"]}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        (grant,) = AgentGrant.objects.all()
        assert grant.scopes == ["profile", "time:read"]

    def test_it_is_written_down_by_field_and_not_by_value(self, admin, bot):
        admin.patch(
            url(bot.client.client_id),
            {"name": "Secretive name", "is_active": False},
            format="json",
            HTTP_ORIGIN=OWN_ORIGIN,
        )
        (line,) = AgentAuditLog.objects.filter(event="app_changed")
        assert line.detail == {"fields": ["name", "is_active"]}

    def test_nothing_changed_nothing_written(self, admin, bot):
        admin.patch(url(bot.client.client_id), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        assert not AgentAuditLog.objects.filter(event="app_changed").exists()

    def test_a_form_saved_as_it_was_changes_nothing_and_writes_nothing(self, admin, bot):
        before = AgentClient.objects.get(pk=bot.client.pk)
        response = admin.patch(
            url(bot.client.client_id),
            {
                "name": before.name,
                "description": before.description,
                "redirect_uris": before.redirect_uris,
                "allowed_scopes": before.allowed_scopes,
                "is_active": before.is_active,
            },
            format="json",
            HTTP_ORIGIN=OWN_ORIGIN,
        )
        assert response.status_code == 200
        assert not AgentAuditLog.objects.filter(event="app_changed").exists()

    def test_only_what_really_differs_is_written_down(self, admin, bot):
        admin.patch(
            url(bot.client.client_id),
            {"name": "Telegram bot", "description": "New words", "redirect_uris": [REDIRECT_URI]},
            format="json",
            HTTP_ORIGIN=OWN_ORIGIN,
        )
        (line,) = AgentAuditLog.objects.filter(event="app_changed")
        assert line.detail == {"fields": ["description"]}

    def test_an_unknown_app_is_not_found(self, admin):
        assert admin.get(url("plane_client_nope")).status_code == 404
        assert admin.patch(url("plane_client_nope"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN).status_code == 404


class TestTheSecret:
    def test_a_new_one_replaces_the_old_one_at_once(self, admin, bot):
        old = bot.secret
        response = admin.post(url(bot.client.client_id, "secret"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN)

        assert response.status_code == 200
        new = response.json()["client_secret"]
        assert new != old and new.startswith("plane_cs_")
        bot.client.refresh_from_db()
        assert bot.client.secret_hash == hash_secret(new) and bot.client.secret_rotated_at is not None
        assert bot.refresh("plane_rt_unknown", auth=bot.credentials(secret=old)).status_code == 401

    def test_it_is_not_in_the_log(self, admin, bot):
        new = admin.post(url(bot.client.client_id, "secret"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN).json()[
            "client_secret"
        ]
        (line,) = AgentAuditLog.objects.filter(event="app_secret_replaced")
        assert new not in str(line.detail)

    def test_it_is_a_post_so_a_page_cannot_make_a_browser_do_it(self, admin, bot):
        assert admin.get(url(bot.client.client_id, "secret")).status_code == 405


class TestEvents:
    def test_an_address_is_set_and_a_dead_app_is_switched_back_on(self, admin, bot, monkeypatch):
        monkeypatch.setattr(events, "validate_url", lambda *args, **kwargs: None)
        AgentClient.objects.filter(pk=bot.client.pk).update(webhook_disabled_at=timezone.now(), webhook_failures=10)

        response = admin.put(
            url(bot.client.client_id, "webhook"),
            {"url": "https://bot.example.com/new"},
            format="json",
            HTTP_ORIGIN=OWN_ORIGIN,
        )

        assert response.status_code == 200
        assert response.json()["webhook"] == {
            "url": "https://bot.example.com/new",
            "state": "on",
            "failures": 0,
            "disabled_at": None,
        }

    def test_an_app_that_was_given_up_on_says_so(self, admin, bot):
        AgentClient.objects.filter(pk=bot.client.pk).update(webhook_disabled_at=timezone.now(), webhook_failures=10)
        webhook = admin.get(url(bot.client.client_id)).json()["webhook"]
        assert webhook["state"] == "given_up" and webhook["failures"] == 10

    @pytest.mark.parametrize(
        "address",
        [
            "",
            "   ",
            "http://bot.example.com/hook",
            "https://127.0.0.1/hook",
            "https://169.254.169.254/latest/meta-data",
            "https://user:pass@bot.example.com/hook",
            "ftp://bot.example.com/hook",
        ],
    )
    def test_an_address_that_is_not_safe_is_refused_and_the_old_one_stays(self, admin, bot, address):
        response = admin.put(
            url(bot.client.client_id, "webhook"), {"url": address}, format="json", HTTP_ORIGIN=OWN_ORIGIN
        )
        assert response.status_code == 400 and response.json()["error"]
        bot.client.refresh_from_db()
        assert bot.client.webhook_url == HOOK

    def test_off_means_off(self, admin, bot):
        response = admin.delete(url(bot.client.client_id, "webhook"), HTTP_ORIGIN=OWN_ORIGIN)
        assert response.status_code == 200 and response.json()["webhook"]["state"] == "off"
        bot.client.refresh_from_db()
        assert bot.client.webhook_url == ""

    def test_the_signing_secret_can_be_shown_again(self, admin, bot):
        first = admin.post(url(bot.client.client_id, "webhook", "secret"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        second = admin.post(url(bot.client.client_id, "webhook", "secret"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        assert first.json()["webhook_secret"] == second.json()["webhook_secret"] == events.webhook_secret(bot.client)

    def test_a_new_signing_secret_replaces_the_old_one_at_once(self, admin, bot):
        before = events.webhook_secret(bot.client)
        response = admin.post(
            url(bot.client.client_id, "webhook", "secret"), {"replace": True}, format="json", HTTP_ORIGIN=OWN_ORIGIN
        )
        bot.client.refresh_from_db()
        assert response.json()["webhook_secret"] == events.webhook_secret(bot.client) != before

    def test_asking_to_see_the_secret_is_written_down_but_the_secret_is_not(self, admin, bot):
        admin.post(url(bot.client.client_id, "webhook", "secret"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        (line,) = AgentAuditLog.objects.filter(event="app_events_secret")
        assert line.detail == {"replaced": False}
        assert events.webhook_secret(bot.client) not in str(line.detail)

    def test_the_secret_is_never_in_the_ordinary_answers(self, admin, bot, monkeypatch):
        monkeypatch.setattr(events, "validate_url", lambda *args, **kwargs: None)
        secret = events.webhook_secret(bot.client)
        for response in (
            admin.get(APPS),
            admin.get(url(bot.client.client_id)),
            admin.put(url(bot.client.client_id, "webhook"), {"url": HOOK}, format="json", HTTP_ORIGIN=OWN_ORIGIN),
        ):
            assert secret not in response.content.decode()

    def test_a_test_reports_whether_the_app_answered(self, admin, bot, monkeypatch):
        monkeypatch.setattr(events, "send_test", lambda client: (True, "HTTP 200"))
        response = admin.post(url(bot.client.client_id, "webhook", "test"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        assert response.status_code == 200 and response.json() == {"heard": True, "detail": "HTTP 200"}

        monkeypatch.setattr(events, "send_test", lambda client: (False, "HTTP 503"))
        response = admin.post(url(bot.client.client_id, "webhook", "test"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        assert response.json() == {"heard": False, "detail": "HTTP 503"}

    def test_a_test_really_sends_one_signed_message(self, admin, bot, monkeypatch):
        sent = SimpleNamespace(calls=[])

        class Answer:
            status_code = 204

            def close(self):
                pass

        monkeypatch.setattr(events, "pinned_fetch", lambda method, url, **kwargs: sent.calls.append(kwargs) or Answer())
        response = admin.post(url(bot.client.client_id, "webhook", "test"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        assert response.json() == {"heard": True, "detail": "HTTP 204"}
        (call,) = sent.calls
        assert call["headers"]["X-Plane-Agent-Event"] == "webhook.test"

    def test_there_is_nothing_to_test_without_an_address(self, admin, make_app):
        app = make_app(name="Quiet")
        response = admin.post(url(app.client.client_id, "webhook", "test"), {}, format="json", HTTP_ORIGIN=OWN_ORIGIN)
        assert response.status_code == 400


class TestConnections:
    def test_they_are_listed_with_who_and_since_when_and_never_a_token(self, admin, bot, person):
        tokens = bot.link(person, scope="profile time:read")
        body = admin.get(url(bot.client.client_id, "connections")).json()

        assert body["total"] == 1
        (row,) = body["results"]
        assert row["user"]["email"] == person.email and row["user"]["display_name"] == person.display_name
        assert row["scopes"] == ["profile", "time:read"]
        assert row["account"] == {"provider": "telegram", "username": "mallory", "name": "Mallory Test"}
        raw = str(body)
        assert tokens["access_token"] not in raw and tokens["refresh_token"] not in raw

    def test_one_can_be_ended_and_its_tokens_stop_at_once(self, admin, bot, person):
        from plane.tests.contract.agent.conftest import bearer

        tokens = bot.link(person, scope="profile")
        (grant,) = AgentGrant.objects.all()

        response = admin.delete(url(bot.client.client_id, "connections", str(grant.id)), HTTP_ORIGIN=OWN_ORIGIN)

        assert response.status_code == 200 and response.json()["ended"] == 1
        assert response.json()["app"]["connections"] == 0
        grant.refresh_from_db()
        assert grant.revoked_reason == "admin"
        assert bearer(tokens["access_token"]).get("/api/agent/v1/me/").status_code == 401

    def test_all_of_them_can_be_ended(self, admin, bot, person):
        bot.link(person, scope="profile")
        other = make_user()
        bot.link(other, scope="profile", account_id="7")

        response = admin.delete(url(bot.client.client_id, "connections"), HTTP_ORIGIN=OWN_ORIGIN)

        assert response.json()["ended"] == 2
        assert not AgentGrant.objects.filter(revoked_at__isnull=True).exists()

    def test_another_apps_connection_cannot_be_ended_through_this_one(self, admin, bot, make_app, person):
        other_app = make_app(name="Other")
        other_app.link(person, scope="profile")
        (grant,) = AgentGrant.objects.all()

        response = admin.delete(url(bot.client.client_id, "connections", str(grant.id)), HTTP_ORIGIN=OWN_ORIGIN)

        assert response.status_code == 404
        grant.refresh_from_db()
        assert grant.revoked_at is None

    def test_ending_them_is_written_down(self, admin, bot, person):
        bot.link(person, scope="profile")
        admin.delete(url(bot.client.client_id, "connections"), HTTP_ORIGIN=OWN_ORIGIN)
        (line,) = AgentAuditLog.objects.filter(event="app_connections_ended")
        assert line.detail == {"count": 1, "all": True}
