# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A connected app's token reaches connected-app endpoints and nothing else, and they accept nothing else.

Each way in is separate on purpose. If a bot's token could be used as a browser
session, or a session or an API key could call the bot endpoints, a leak of one kind
of credential would become a leak of all of them.
"""

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.agent.scopes import SCOPES
from plane.agent.urls import v1_patterns
from plane.agent.views.base import AgentAPIView
from plane.db.models import APIToken
from plane.tests.contract.agent.conftest import ME_URL, bearer

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


class TestTheTokenWorksOnlyOnConnectedAppEndpoints:
    @pytest.mark.parametrize("path", ["/api/users/me/", "/api/v1/users/me/", "/api/hr/me/", "/api/workspaces/"])
    def test_it_is_not_a_session_or_an_api_key(self, linked, path):
        assert bearer(linked["access_token"]).get(path).status_code in (401, 403)

    def test_it_is_not_accepted_as_an_api_key(self, linked):
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=linked["access_token"])
        assert client.get("/api/v1/users/me/").status_code in (401, 403)


class TestConnectedAppEndpointsAcceptOnlyTheirOwnTokens:
    def test_a_browser_session_is_not_enough(self, app, person):
        assert app.browser(person).get(ME_URL).status_code == 401

    def test_an_api_key_is_not_enough(self, person):
        token = APIToken.objects.create(user=person, label="key", token="plane_api_test_key_value")
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=token.token, HTTP_AUTHORIZATION=f"Bearer {token.token}")
        assert client.get(ME_URL).status_code == 401

    def test_nothing_is_not_enough_and_the_answer_says_what_is_expected(self):
        response = APIClient().get(ME_URL)
        assert response.status_code == 401
        assert response["WWW-Authenticate"].startswith("Bearer")
        assert response.json()["error"] == "unauthorized"

    def test_a_token_in_the_address_is_ignored(self, linked):
        """Addresses are written to logs along the way. A token there would end up in all of them."""
        assert APIClient().get(f"{ME_URL}?access_token={linked['access_token']}").status_code == 401

    @pytest.mark.parametrize(
        "header",
        [
            "Bearer",
            "Bearer ",
            "Bearer a b",
            "Basic abc",
            "Bearer plane_api_not_an_agent_token",
            "Bearer plane_at_invented",
        ],
    )
    def test_a_malformed_or_foreign_credential_is_refused(self, header):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=header)
        assert client.get(ME_URL).status_code == 401

    def test_the_refresh_token_is_not_an_access_token(self, linked):
        assert bearer(linked["refresh_token"]).get(ME_URL).status_code == 401


class TestScopes:
    def test_a_token_reaches_what_its_scopes_name(self, app, person):
        tokens = app.link(person, scope="profile")
        assert bearer(tokens["access_token"]).get(ME_URL).status_code == 200

    def test_a_token_without_the_scope_is_told_which_one_is_missing(self, app, person):
        tokens = app.link(person, scope="time:read")
        response = bearer(tokens["access_token"]).get(ME_URL)
        assert response.status_code == 403
        assert response.json()["error"] == "insufficient_scope"
        assert response.json()["scope"] == "profile"
        assert 'error="insufficient_scope"' in response["WWW-Authenticate"]

    def test_the_connection_reports_only_what_it_was_given(self, app, person):
        tokens = app.link(person, scope="profile time:read")
        scopes = [scope["id"] for scope in bearer(tokens["access_token"]).get(ME_URL).json()["connection"]["scopes"]]
        assert scopes == ["profile", "time:read"]

    def test_every_endpoint_names_a_known_scope(self):
        """A view that names none is refused outright, so this catches the one that was meant to work."""
        views = [
            pattern.callback.view_class
            for pattern in v1_patterns
            if issubclass(getattr(pattern.callback, "view_class", object), AgentAPIView)
        ]
        assert views
        for view in views:
            assert view.required_scope in SCOPES, view

    def test_a_view_that_names_no_scope_is_refused(self, linked, monkeypatch):
        from plane.agent.views.me import MeEndpoint

        monkeypatch.setattr(MeEndpoint, "required_scope", None)
        assert bearer(linked["access_token"]).get(ME_URL).status_code == 403


class TestResponses:
    def test_nothing_is_cached(self, linked):
        response = bearer(linked["access_token"]).get(ME_URL)
        assert response["Cache-Control"] == "no-store"

    def test_only_reads_are_accepted(self, linked):
        client = bearer(linked["access_token"])
        for method in (client.post, client.put, client.patch, client.delete):
            assert method(ME_URL, {}, format="json").status_code == 405

    def test_the_person_is_whoever_linked_the_app(self, person, linked):
        body = bearer(linked["access_token"]).get(ME_URL).json()
        assert body["id"] == str(person.id)
        assert body["connection"]["account"]["id"] == "424242"

    def test_calls_are_written_to_the_audit_log_without_their_content(self, linked):
        from plane.agent.models import AgentAuditLog

        bearer(linked["access_token"]).get(f"{ME_URL}?secret=value")
        line = AgentAuditLog.objects.filter(event="api").get()
        assert line.path == ME_URL and line.method == "GET" and line.status_code == 200
        assert "secret" not in str(line.detail) + line.path
