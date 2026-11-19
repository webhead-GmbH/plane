# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Registering apps, cleaning up after them, and the text rules the consent screen relies on."""

# Python imports
from datetime import timedelta
from io import StringIO

# Third-party imports
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

# Module imports
from plane.agent.models import AgentAuditLog, AgentAuthorizationRequest, AgentClient, AgentGrant, AgentToken
from plane.agent.oauth import validate_redirect_uri
from plane.agent.scopes import READ_ONLY_SCOPES, SCOPES, describe, parse_scope_string
from plane.agent.tasks import purge_expired
from plane.agent.text import clean_display_text
from plane.agent.tokens import hash_secret
from plane.tests.contract.agent.conftest import ME_URL, bearer

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def run(*args):
    out = StringIO()
    call_command("agent_client", *args, stdout=out)
    return out.getvalue()


def credentials_from(output):
    client_id = next(line.split(":", 1)[1].strip() for line in output.splitlines() if "client_id:" in line)
    secret = next(line.split(":", 1)[1].strip() for line in output.splitlines() if "client_secret:" in line)
    return client_id, secret


class TestRegisteringApps:
    def test_creating_an_app_shows_its_secret_once_and_keeps_only_a_hash(self):
        output = run("create", "--name", "Bot", "--redirect-uri", "https://bot.example.com/cb")
        client_id, secret = credentials_from(output)
        client = AgentClient.objects.get(client_id=client_id)
        assert secret.startswith("plane_cs_") and client_id.startswith("plane_client_")
        assert client.secret_hash == hash_secret(secret) and secret not in client.secret_hash
        assert client.allowed_scopes == READ_ONLY_SCOPES and client.redirect_uris == ["https://bot.example.com/cb"]
        assert not set(client.allowed_scopes) & {"work_items:write", "time:write"}, "changing things is opt-in"
        assert secret not in run("list")

    def test_scopes_that_change_things_have_to_be_named(self):
        run("create", "--name", "Writer", "--redirect-uri", "https://b.example.com/cb", "--scope", "work_items:write")
        assert AgentClient.objects.get().allowed_scopes == ["work_items:write"]

    def test_scopes_can_be_narrowed_and_unknown_ones_are_refused(self):
        run("create", "--name", "Bot", "--redirect-uri", "https://b.example.com/cb", "--scope", "profile")
        assert AgentClient.objects.get().allowed_scopes == ["profile"]
        with pytest.raises(CommandError):
            run("create", "--name", "Bot2", "--redirect-uri", "https://b.example.com/cb", "--scope", "root")

    @pytest.mark.parametrize(
        ("uri", "ok"),
        [
            ("https://bot.example.com/cb", True),
            ("http://localhost:9001/cb", True),
            ("http://127.0.0.1:9001/cb", True),
            ("http://bot.example.com/cb", False),
            ("http://localhost.evil.example/cb", False),
            ("https://bot.example.com/cb#frag", False),
            ("https://user:pass@bot.example.com/cb", False),
            ("ftp://bot.example.com/cb", False),
            ("javascript:alert(1)", False),
            ("/relative/path", False),
            ("", False),
        ],
    )
    def test_only_safe_redirect_addresses_can_be_registered(self, uri, ok):
        assert (validate_redirect_uri(uri) is None) is ok
        if not ok:
            with pytest.raises(CommandError):
                run("create", "--name", "Bot", "--redirect-uri", uri)

    def test_a_new_secret_replaces_the_old_one_at_once(self, app, person):
        output = run("rotate-secret", app.client.client_id)
        _, new_secret = credentials_from(output.replace("New secret", "client_id: x\nNew secret"))
        assert app.link_request()[0].status_code == 401, "the old secret no longer works"
        assert new_secret and AgentClient.objects.get().secret_hash == hash_secret(new_secret)

    def test_switching_an_app_off_and_on(self, app, linked):
        run("deactivate", app.client.client_id)
        assert bearer(linked["access_token"]).get(ME_URL).status_code == 401
        run("activate", app.client.client_id)
        assert bearer(linked["access_token"]).get(ME_URL).status_code == 200

    def test_redirect_addresses_can_be_added_and_removed_but_not_all(self, app):
        run("update", app.client.client_id, "--add-redirect-uri", "https://bot.example.com/second")
        assert len(AgentClient.objects.get().redirect_uris) == 2
        with pytest.raises(CommandError):
            run(
                "update",
                app.client.client_id,
                "--remove-redirect-uri",
                "https://bot.example.com/plane/callback",
                "--remove-redirect-uri",
                "https://bot.example.com/second",
            )

    def test_every_connection_of_an_app_can_be_ended_or_one_persons(self, app, person, linked):
        from plane.tests.contract.agent.world import make_user

        other = make_user()
        other_tokens = app.link(other)
        run("revoke-grants", app.client.client_id, "--email", person.email)
        assert bearer(linked["access_token"]).get(ME_URL).status_code == 401
        assert bearer(other_tokens["access_token"]).get(ME_URL).status_code == 200
        run("revoke-grants", app.client.client_id)
        assert bearer(other_tokens["access_token"]).get(ME_URL).status_code == 401
        assert set(AgentGrant.objects.values_list("revoked_reason", flat=True)) == {"admin"}

    def test_an_unknown_app_is_an_error(self):
        with pytest.raises(CommandError):
            run("deactivate", "plane_client_nope")


class TestCleaningUp:
    def test_old_requests_and_tokens_go_and_the_history_of_who_had_access_stays(self, app, linked):
        long_ago = timezone.now() - timedelta(days=30)
        AgentAuthorizationRequest.objects.update(expires_at=long_ago)
        AgentToken.objects.update(expires_at=long_ago)
        AgentAuditLog.objects.create(event="api", created_at=timezone.now() - timedelta(days=400))
        AgentAuditLog.objects.create(event="api")

        removed = purge_expired()

        assert removed["requests"] == 1 and removed["tokens"] == 2 and removed["audit_lines"] == 1
        assert AgentGrant.objects.count() == 1
        assert AgentAuditLog.objects.filter(event="api").count() == 1

    def test_what_is_still_in_force_is_left_alone(self, linked):
        assert purge_expired()["tokens"] == 0
        assert AgentToken.objects.count() == 2


class TestTextFromOtherApps:
    @pytest.mark.parametrize(
        ("raw", "clean"),
        [
            ("Mallory", "Mallory"),
            ("  Mallory \n Test\t", "Mallory Test"),
            ("‮yrolla M", "yrolla M"),
            ("Mal​lory", "Mallory"),
            ("a⁦b⁩c", "abc"),
            ("﻿name", "name"),
            ("علی رضایی", "علی رضایی"),
            ("می‌خواهم", "می‌خواهم"),
            ("👨‍👩‍👧", "👨‍👩‍👧"),
            ("x" * 500, "x" * 20),
            (None, ""),
            (12345, "12345"),
        ],
    )
    def test_invisible_and_layout_characters_are_removed_and_real_text_is_kept(self, raw, clean):
        assert clean_display_text(raw, 20) == clean

    def test_scopes_are_listed_in_order_without_repeats_and_described_for_the_screen(self):
        assert parse_scope_string("profile time:read  profile") == ["profile", "time:read"]
        assert [scope["id"] for scope in describe(["time:read", "bogus"])] == ["time:read"]
        assert all(scope["title"] and scope["description"] for scope in describe(list(SCOPES)))


class TestWhereACallComesFrom:
    @staticmethod
    def address(monkeypatch, proxies, forwarded=None, remote="198.51.100.7"):
        from types import SimpleNamespace

        from django.test import RequestFactory

        from plane.agent import network

        monkeypatch.setattr(network, "api_settings", SimpleNamespace(NUM_PROXIES=proxies))
        extra = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded else {}
        return network.client_address(RequestFactory().get("/", REMOTE_ADDR=remote, **extra))

    def test_without_a_known_proxy_the_header_is_not_believed(self, monkeypatch):
        assert self.address(monkeypatch, None, "203.0.113.9") == "198.51.100.7"

    def test_behind_one_proxy_the_address_that_proxy_wrote_is_used_not_the_one_the_caller_claimed(self, monkeypatch):
        assert self.address(monkeypatch, 1, "6.6.6.6, 203.0.113.9") == "203.0.113.9"

    def test_behind_two_proxies(self, monkeypatch):
        assert self.address(monkeypatch, 2, "6.6.6.6, 203.0.113.9, 10.0.0.2") == "203.0.113.9"

    def test_something_that_is_not_an_address_is_nothing(self, monkeypatch):
        assert self.address(monkeypatch, 1, "not-an-ip") is None
