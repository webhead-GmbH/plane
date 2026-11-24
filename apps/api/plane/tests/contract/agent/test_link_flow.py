# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Linking a person to an app: asking, approving, and spending the approval.

The cases here are the ways this goes wrong in practice. A link that can be altered on
its way to the person, an approval that a stranger's web page can trigger, a code that
works for whoever holds it, and an address the person ends up sent to that nobody
registered, each turn "the person said yes" into "somebody else got in".
"""

# Python imports
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

# Third-party imports
import pytest
from django.utils import timezone

# Module imports
from plane.agent.models import AgentAuthorizationRequest, AgentGrant
from plane.agent.tokens import hash_secret
from plane.tests.contract.agent.conftest import ALL_SCOPES, OWN_ORIGIN, REDIRECT_URI, REQUESTS_URL, bearer
from plane.tests.factories import UserFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def _error(response):
    return response.json()["error"]


class TestAskingForALink:
    def test_the_app_gets_a_link_and_a_lifetime(self, app):
        response, _ = app.link_request()
        assert response.status_code == 201
        body = response.json()
        assert "/connect/agent/plane_ar_" in body["authorization_url"]
        assert body["expires_in"] == 600

    def test_the_link_is_stored_as_a_hash(self, app):
        response, _ = app.link_request()
        token = app.request_token_from(response)
        row = AgentAuthorizationRequest.objects.get()
        assert row.request_hash == hash_secret(token)
        assert token not in {row.request_hash, row.redirect_uri, row.client_state}

    def test_a_wrong_secret_is_refused_without_saying_whether_the_client_exists(self, app):
        wrong_secret = app.link_request(auth=app.credentials(secret="plane_cs_wrong"))[0]
        unknown_client = app.link_request(auth=app.credentials(client_id="plane_client_nobody"))[0]
        assert wrong_secret.status_code == unknown_client.status_code == 401
        assert wrong_secret.json() == unknown_client.json()
        assert _error(wrong_secret) == "invalid_client"
        assert wrong_secret["WWW-Authenticate"].startswith("Basic")

    def test_a_switched_off_app_is_refused(self, app):
        app.client.is_active = False
        app.client.save()
        assert app.link_request()[0].status_code == 401

    def test_the_secret_in_the_address_is_not_accepted(self, app):
        """Addresses are logged by every proxy on the way. A secret there would be in all of them."""
        response = app.http.post(
            f"{REQUESTS_URL}?client_id={app.client.client_id}&client_secret={app.secret}", {}, format="json"
        )
        assert response.status_code == 401

    def test_the_secret_in_the_body_is_accepted_for_clients_that_cannot_send_a_header(self, app):
        response, _ = app.link_request(auth={}, client_id=app.client.client_id, client_secret=app.secret)
        assert response.status_code == 201

    @pytest.mark.parametrize(
        "uri",
        [
            "https://bot.example.com/plane/callback/extra",
            "https://bot.example.com/plane/callback?next=https://evil.example",
            "https://bot.example.com.evil.example/plane/callback",
            "https://evil.example/plane/callback",
            "http://bot.example.com/plane/callback",
            "https://BOT.example.com/plane/callback",
            "https://bot.example.com/plane/callback#",
            "",
        ],
    )
    def test_only_a_registered_address_is_accepted_exactly(self, app, uri):
        response, _ = app.link_request(redirect_uri=uri)
        assert response.status_code == 400
        assert AgentAuthorizationRequest.objects.count() == 0

    def test_scopes_must_be_known_and_allowed_for_the_app(self, app, make_app):
        assert _error(app.link_request(scope="profile everything")[0]) == "invalid_scope"
        narrow = make_app(allowed_scopes=["profile"])
        assert _error(narrow.link_request(scope="profile time:read")[0]) == "invalid_scope"
        assert narrow.link_request(scope="profile")[0].status_code == 201

    def test_a_request_with_no_scope_is_refused(self, app):
        assert app.link_request(scope="")[0].status_code == 400

    @pytest.mark.parametrize("override", [{"code_challenge_method": "plain"}, {"code_challenge_method": None}])
    def test_only_s256_is_accepted(self, app, override):
        assert app.link_request(**override)[0].status_code == 400

    def test_a_malformed_challenge_is_refused(self, app):
        assert app.link_request(code_challenge="short")[0].status_code == 400
        assert app.link_request(code_challenge=None)[0].status_code == 400

    def test_state_and_the_account_being_linked_are_required(self, app):
        assert app.link_request(state=None)[0].status_code == 400
        assert app.link_request(account_id=None)[0].status_code == 400
        assert app.link_request(account_provider=None)[0].status_code == 400
        assert app.link_request(account_provider="Not A Provider!")[0].status_code == 400

    def test_what_the_app_says_about_the_account_is_cleaned_before_anybody_sees_it(self, app):
        """A right-to-left override makes a handle read backwards; invisible characters make two names look alike."""
        app.link_request(account_username="‮allory‬", account_name="Mal​lory\n Test⁦")
        row = AgentAuthorizationRequest.objects.get()
        assert row.account_username == "allory"
        assert row.account_name == "Mallory Test"

    def test_persian_names_keep_their_joiners(self, app):
        app.link_request(account_name="می‌خواهم علی")
        assert AgentAuthorizationRequest.objects.get().account_name == "می‌خواهم علی"

    def test_the_app_is_throttled_by_address(self, app, monkeypatch):
        from plane.agent.throttles import OAuthRateThrottle

        monkeypatch.setattr(OAuthRateThrottle, "rate", "2/minute")
        # Each call claims a different origin in a header the caller writes. That must not buy a fresh allowance.
        responses = [
            app.link_request(auth={**app.credentials(), "HTTP_X_FORWARDED_FOR": f"203.0.113.{number}"})[0]
            for number in range(4)
        ]
        assert [response.status_code for response in responses] == [201, 201, 429, 429]
        assert responses[2]["Retry-After"]
        assert responses[2].json()["error"] == "rate_limited"


class TestApproving:
    def test_the_person_is_shown_who_is_asking_and_what_for(self, app, person):
        response, _ = app.link_request(account_username="mallory", account_name="Mallory Test")
        shown = app.consent(person, app.request_token_from(response)).json()
        assert shown["client"]["name"] == "Test bot"
        assert shown["account"] == {
            "provider": "telegram",
            "id": "424242",
            "username": "mallory",
            "name": "Mallory Test",
        }
        assert [scope["id"] for scope in shown["scopes"]] == ALL_SCOPES.split()
        assert shown["user"]["email"] == person.email
        assert shown["nonce"]

    def test_the_consent_page_needs_a_signed_in_person(self, app):
        response, _ = app.link_request()
        from rest_framework.test import APIClient

        assert APIClient().get(f"/api/agent/connect/{app.request_token_from(response)}/").status_code in (401, 403)

    @pytest.mark.parametrize("token", ["plane_ar_unknown", "nonsense", "plane_cs_" + "x" * 40])
    def test_an_unknown_link_shows_nothing(self, app, person, token):
        assert app.consent(person, token).status_code == 404

    def test_an_expired_link_shows_nothing(self, app, person):
        response, _ = app.link_request()
        AgentAuthorizationRequest.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        assert app.consent(person, app.request_token_from(response)).status_code == 404

    def test_approving_sends_the_person_back_to_the_registered_address_with_a_code_and_the_apps_state(
        self, app, person
    ):
        response, _ = app.link_request(state="my-state-123")
        link = app.request_token_from(response)
        nonce = app.consent(person, link).json()["nonce"]
        approved = app.decide(person, link, nonce)
        assert approved.status_code == 200
        target = urlsplit(approved.json()["redirect_to"])
        assert f"{target.scheme}://{target.netloc}{target.path}" == REDIRECT_URI
        query = parse_qs(target.query)
        assert query["state"] == ["my-state-123"]
        assert query["code"][0].startswith("plane_ac_")

    def test_the_code_is_stored_as_a_hash_and_is_short_lived(self, app, person):
        response, _ = app.link_request()
        link = app.request_token_from(response)
        approved = app.decide(person, link, app.consent(person, link).json()["nonce"])
        code = app.code_from(approved)
        row = AgentAuthorizationRequest.objects.get()
        assert row.code_hash == hash_secret(code)
        assert timedelta(seconds=50) < row.code_expires_at - timezone.now() <= timedelta(seconds=60)

    def test_an_existing_query_on_the_registered_address_is_kept(self, make_app, person):
        app = make_app(redirect_uris=["https://bot.example.com/cb?tenant=acme"])
        response, _ = app.link_request(redirect_uri="https://bot.example.com/cb?tenant=acme")
        link = app.request_token_from(response)
        approved = app.decide(person, link, app.consent(person, link).json()["nonce"])
        query = parse_qs(urlsplit(approved.json()["redirect_to"]).query)
        assert query["tenant"] == ["acme"] and "code" in query

    def test_a_link_can_be_approved_once(self, app, person):
        response, _ = app.link_request()
        link = app.request_token_from(response)
        nonce = app.consent(person, link).json()["nonce"]
        assert app.decide(person, link, nonce).status_code == 200
        assert app.decide(person, link, nonce).status_code == 404

    def test_refusing_sends_the_person_back_with_access_denied_and_no_code(self, app, person):
        response, _ = app.link_request(state="s9")
        link = app.request_token_from(response)
        nonce = app.consent(person, link).json()["nonce"]
        denied = app.decide(person, link, nonce, action="deny")
        query = parse_qs(urlsplit(denied.json()["redirect_to"]).query)
        assert query == {"error": ["access_denied"], "state": ["s9"]}
        assert app.decide(person, link, nonce).status_code == 404

    # --- the ways a web page on another site might try to approve for somebody ---

    def test_approving_needs_the_confirmation_value_the_screen_was_given(self, app, person):
        response, _ = app.link_request()
        link = app.request_token_from(response)
        assert app.decide(person, link, "").status_code == 400
        assert app.decide(person, link, "forged").status_code == 400
        assert AgentAuthorizationRequest.objects.get().status == AgentAuthorizationRequest.Status.PENDING

    def test_the_confirmation_value_is_for_one_person(self, app, person):
        response, _ = app.link_request()
        link = app.request_token_from(response)
        nonce = app.consent(person, link).json()["nonce"]
        other = UserFactory()
        assert app.decide(other, link, nonce).status_code == 400

    def test_the_confirmation_value_is_for_one_link(self, app, person):
        first, _ = app.link_request()
        second, _ = app.link_request()
        nonce = app.consent(person, app.request_token_from(first)).json()["nonce"]
        assert app.decide(person, app.request_token_from(second), nonce).status_code == 400

    @pytest.mark.parametrize("origin", ["https://evil.example", "null", None])
    def test_approving_must_come_from_plane_s_own_pages(self, app, person, origin):
        response, _ = app.link_request()
        link = app.request_token_from(response)
        nonce = app.consent(person, link).json()["nonce"]
        assert app.decide(person, link, nonce, origin=origin).status_code == 403
        assert app.decide(person, link, nonce, origin=origin, action="deny").status_code == 403
        assert AgentAuthorizationRequest.objects.get().status == AgentAuthorizationRequest.Status.PENDING

    def test_approving_must_be_sent_as_json(self, app, person):
        response, _ = app.link_request()
        link = app.request_token_from(response)
        nonce = app.consent(person, link).json()["nonce"]
        assert app.decide(person, link, nonce, content_type="form").status_code in (400, 415)

    def test_a_bot_account_cannot_approve(self, app, create_bot_user):
        response, _ = app.link_request()
        link = app.request_token_from(response)
        nonce = app.consent(create_bot_user, link).json()["nonce"]
        assert app.decide(create_bot_user, link, nonce).status_code == 403


class TestSpendingTheCode:
    def _approved(self, app, person, **overrides):
        response, verifier = app.link_request(**overrides)
        link = app.request_token_from(response)
        approved = app.decide(person, link, app.consent(person, link).json()["nonce"])
        return app.code_from(approved), verifier

    def test_the_code_buys_a_pair_of_tokens(self, app, person):
        code, verifier = self._approved(app, person, scope="profile time:read")
        response = app.exchange(code, verifier)
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 3600
        assert body["scope"] == "profile time:read"
        assert body["access_token"].startswith("plane_at_") and body["refresh_token"].startswith("plane_rt_")
        assert response["Cache-Control"] == "no-store"

    def test_the_grant_records_who_was_linked_and_when_it_ends(self, app, person):
        code, verifier = self._approved(app, person, account_username="mallory")
        app.exchange(code, verifier)
        grant = AgentGrant.objects.get()
        assert grant.user == person and grant.client == app.client
        assert grant.account_provider == "telegram" and grant.account_username == "mallory"
        assert timedelta(days=364) < grant.expires_at - timezone.now() <= timedelta(days=365)

    def test_tokens_are_stored_as_hashes(self, app, person):
        code, verifier = self._approved(app, person)
        body = app.exchange(code, verifier).json()
        from plane.agent.models import AgentToken

        hashes = set(AgentToken.objects.values_list("token_hash", flat=True))
        assert hashes == {hash_secret(body["access_token"]), hash_secret(body["refresh_token"])}

    def test_the_wrong_verifier_gets_nothing_and_spends_the_code(self, app, person):
        """Whoever holds only the code (from a log, a screen) cannot use it, and cannot keep guessing at it."""
        code, verifier = self._approved(app, person)
        assert _error(app.exchange(code, "x" * 50)) == "invalid_grant"
        assert _error(app.exchange(code, verifier)) == "invalid_grant"
        assert AgentGrant.objects.count() == 0

    def test_a_missing_verifier_gets_nothing(self, app, person):
        code, _ = self._approved(app, person)
        response = app.form(
            "/api/agent/v1/oauth/token/",
            {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
        )
        assert response.status_code == 400 and AgentGrant.objects.count() == 0

    def test_the_wrong_redirect_address_gets_nothing(self, app, person):
        code, verifier = self._approved(app, person)
        response = app.exchange(code, verifier, redirect_uri="https://bot.example.com/other")
        assert _error(response) == "invalid_grant"
        assert AgentGrant.objects.count() == 0

    def test_another_app_cannot_spend_the_code(self, app, make_app, person):
        other = make_app(name="Other bot")
        code, verifier = self._approved(app, person)
        assert _error(other.exchange(code, verifier)) == "invalid_grant"
        assert app.exchange(code, verifier).status_code == 200

    def test_the_wrong_secret_gets_nothing(self, app, person):
        code, verifier = self._approved(app, person)
        response = app.exchange(code, verifier, auth=app.credentials(secret="plane_cs_wrong"))
        assert response.status_code == 401

    def test_an_expired_code_gets_nothing(self, app, person):
        code, verifier = self._approved(app, person)
        AgentAuthorizationRequest.objects.update(code_expires_at=timezone.now() - timedelta(seconds=1))
        assert _error(app.exchange(code, verifier)) == "invalid_grant"

    def test_a_code_nobody_approved_gets_nothing(self, app):
        _, verifier = app.link_request()
        assert _error(app.exchange("plane_ac_invented", verifier)) == "invalid_grant"

    def test_using_a_code_twice_ends_the_connection_it_made(self, app, person):
        """A second use means the code was copied: the person's access is cut, not kept alongside the thief's."""
        code, verifier = self._approved(app, person)
        first = app.exchange(code, verifier).json()
        assert bearer(first["access_token"]).get("/api/agent/v1/me/").status_code == 200

        assert _error(app.exchange(code, verifier)) == "invalid_grant"

        assert bearer(first["access_token"]).get("/api/agent/v1/me/").status_code == 401
        assert app.refresh(first["refresh_token"]).status_code == 400
        assert AgentGrant.objects.get().revoked_reason == "code_reuse"

    def test_a_person_who_has_since_been_deactivated_gets_nothing(self, app, person):
        code, verifier = self._approved(app, person)
        person.is_active = False
        person.save()
        assert _error(app.exchange(code, verifier)) == "invalid_grant"

    def test_unknown_grant_types_are_refused(self, app):
        response = app.form("/api/agent/v1/oauth/token/", {"grant_type": "password", "username": "a", "password": "b"})
        assert _error(response) == "unsupported_grant_type"


class TestLinkingAgain:
    def test_linking_the_same_chat_account_again_replaces_the_earlier_connection(self, app, person, linked):
        newer = app.link(person)
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 401
        assert app.refresh(linked["refresh_token"]).status_code == 400
        assert bearer(newer["access_token"]).get("/api/agent/v1/me/").status_code == 200
        assert sorted(AgentGrant.objects.values_list("revoked_reason", flat=True)) == ["", "superseded"]

    def test_a_different_chat_account_is_a_separate_connection(self, app, person, linked):
        other = app.link(person, account_id="999")
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 200
        assert bearer(other["access_token"]).get("/api/agent/v1/me/").status_code == 200

    def test_somebody_elses_connection_to_the_same_chat_account_is_left_alone(self, app, person, linked):
        colleague = UserFactory()
        app.link(colleague)
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 200


class TestRefreshing:
    def test_a_refresh_token_is_replaced_every_time(self, app, linked):
        first = app.refresh(linked["refresh_token"]).json()
        assert first["refresh_token"] != linked["refresh_token"]
        assert bearer(first["access_token"]).get("/api/agent/v1/me/").status_code == 200
        second = app.refresh(first["refresh_token"])
        assert second.status_code == 200

    def test_a_spent_refresh_token_used_again_later_ends_the_connection(self, app, linked):
        """It was copied. Both holders are cut off; the person links again, which is the safe direction to fail."""
        from plane.agent.models import AgentToken

        fresh = app.refresh(linked["refresh_token"]).json()
        AgentToken.objects.filter(token_hash=hash_secret(linked["refresh_token"])).update(
            used_at=timezone.now() - timedelta(minutes=5)
        )

        assert _error(app.refresh(linked["refresh_token"])) == "invalid_grant"

        assert bearer(fresh["access_token"]).get("/api/agent/v1/me/").status_code == 401
        assert app.refresh(fresh["refresh_token"]).status_code == 400
        assert AgentGrant.objects.get().revoked_reason == "token_reuse"

    def test_two_calls_with_the_same_refresh_token_at_once_are_one_app_retrying(self, app, linked):
        first = app.refresh(linked["refresh_token"])
        retry = app.refresh(linked["refresh_token"])
        assert first.status_code == retry.status_code == 200
        assert AgentGrant.objects.get().revoked_at is None

    def test_another_apps_refresh_token_is_refused(self, app, make_app, linked):
        other = make_app(name="Other")
        assert _error(other.refresh(linked["refresh_token"])) == "invalid_grant"
        assert AgentGrant.objects.get().revoked_at is None

    def test_an_access_token_is_not_a_refresh_token(self, app, linked):
        assert _error(app.refresh(linked["access_token"])) == "invalid_grant"

    def test_an_expired_refresh_token_is_refused(self, app, linked):
        from plane.agent.models import AgentToken

        AgentToken.objects.filter(kind="refresh").update(expires_at=timezone.now() - timedelta(seconds=1))
        assert _error(app.refresh(linked["refresh_token"])) == "invalid_grant"

    def test_nothing_outlives_the_grants_own_limit(self, app, linked):
        grant = AgentGrant.objects.get()
        grant.expires_at = timezone.now() + timedelta(minutes=10)
        grant.save()
        body = app.refresh(linked["refresh_token"]).json()
        assert body["expires_in"] <= 600

    def test_a_connection_past_its_limit_cannot_be_refreshed(self, app, linked):
        AgentGrant.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        assert _error(app.refresh(linked["refresh_token"])) == "invalid_grant"

    def test_a_deactivated_person_cannot_refresh(self, app, linked, person):
        person.is_active = False
        person.save()
        assert _error(app.refresh(linked["refresh_token"])) == "invalid_grant"


class TestTakingAccessBack:
    def test_the_app_can_give_a_refresh_token_back_and_the_connection_ends(self, app, linked):
        assert app.revoke(linked["refresh_token"]).status_code == 200
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 401
        assert app.refresh(linked["refresh_token"]).status_code == 400

    def test_giving_back_only_an_access_token_ends_only_that_token(self, app, linked):
        assert app.revoke(linked["access_token"]).status_code == 200
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 401
        assert app.refresh(linked["refresh_token"]).status_code == 200

    def test_giving_back_an_unknown_token_is_not_an_error(self, app):
        assert app.revoke("plane_rt_never_issued").status_code == 200

    def test_an_app_cannot_revoke_another_apps_token(self, app, make_app, linked):
        make_app(name="Other").revoke(linked["refresh_token"])
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 200

    def test_the_person_sees_their_connections_and_ends_one(self, app, person, linked):
        browser = app.browser(person)
        listed = browser.get("/api/agent/connections/").json()
        assert len(listed) == 1
        entry = listed[0]
        assert entry["app"]["name"] == "Test bot" and entry["account"]["id"] == "424242"
        assert "token" not in str(entry).lower()

        assert browser.delete(f"/api/agent/connections/{entry['id']}/", HTTP_ORIGIN=OWN_ORIGIN).status_code == 204

        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 401
        assert browser.get("/api/agent/connections/").json() == []
        assert AgentGrant.objects.get().revoked_reason == "user"

    def test_ending_a_connection_needs_plane_s_own_pages(self, app, person, linked):
        entry = app.browser(person).get("/api/agent/connections/").json()[0]
        response = app.browser(person).delete(
            f"/api/agent/connections/{entry['id']}/", HTTP_ORIGIN="https://evil.example"
        )
        assert response.status_code == 403
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 200

    def test_nobody_sees_or_ends_somebody_elses_connection(self, app, person, linked):
        stranger = app.browser(UserFactory())
        assert stranger.get("/api/agent/connections/").json() == []
        entry = app.browser(person).get("/api/agent/connections/").json()[0]
        assert stranger.delete(f"/api/agent/connections/{entry['id']}/", HTTP_ORIGIN=OWN_ORIGIN).status_code == 404
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 200

    def test_switching_the_app_off_ends_every_connection_on_its_next_call(self, app, linked):
        app.client.is_active = False
        app.client.save()
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 401
        assert app.refresh(linked["refresh_token"]).status_code == 401

    def test_deactivating_the_person_ends_their_connections_on_the_next_call(self, linked, person):
        person.is_active = False
        person.save()
        assert bearer(linked["access_token"]).get("/api/agent/v1/me/").status_code == 401

    def test_an_expired_access_token_is_refused(self, linked):
        from plane.agent.models import AgentToken

        AgentToken.objects.filter(kind="access").update(expires_at=timezone.now() - timedelta(seconds=1))
        response = bearer(linked["access_token"]).get("/api/agent/v1/me/")
        assert response.status_code == 401
        assert 'error="invalid_token"' in response["WWW-Authenticate"]
