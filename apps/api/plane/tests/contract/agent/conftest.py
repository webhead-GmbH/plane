# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Fixtures for the connected-app tests: a registered app, and a way to link a person to it."""

# Python imports
import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.agent.models import AgentClient
from plane.agent.scopes import SCOPES
from plane.agent.tokens import hash_secret

REDIRECT_URI = "https://bot.example.com/plane/callback"
REQUESTS_URL = "/api/agent/v1/oauth/requests/"
TOKEN_URL = "/api/agent/v1/oauth/token/"
REVOKE_URL = "/api/agent/v1/oauth/revoke/"
ME_URL = "/api/agent/v1/me/"
ALL_SCOPES = " ".join(SCOPES)

# The origin Plane's own web app sends in tests, which is the test client's host.
OWN_ORIGIN = "http://testserver"


def challenge_for(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class BotApp:
    """The registered app, as the developer of a bot would drive it."""

    def __init__(self, client, secret):
        self.client = client
        self.secret = secret
        self.http = APIClient()

    # --- what the app sends ---------------------------------------------------

    def credentials(self, secret=None, client_id=None):
        raw = f"{client_id or self.client.client_id}:{secret or self.secret}"
        return {"HTTP_AUTHORIZATION": "Basic " + base64.b64encode(raw.encode()).decode()}

    def link_request(self, *, scope=ALL_SCOPES, verifier=None, auth=None, **overrides):
        """Ask for a link. Returns the response and the verifier that goes with it."""
        verifier = verifier or secrets.token_urlsafe(48)
        body = {
            "redirect_uri": REDIRECT_URI,
            "scope": scope,
            "state": "state-" + uuid4().hex[:8],
            "code_challenge": challenge_for(verifier),
            "code_challenge_method": "S256",
            "account_provider": "telegram",
            "account_id": "424242",
            "account_username": "mallory",
            "account_name": "Mallory Test",
        }
        body.update(overrides)
        body = {key: value for key, value in body.items() if value is not None}
        response = self.http.post(
            REQUESTS_URL, body, format="json", **(auth if auth is not None else self.credentials())
        )
        return response, verifier

    def form(self, url, body, auth=None):
        """Post the way an OAuth client library does: form-encoded."""
        return self.http.post(
            url,
            urlencode(body),
            content_type="application/x-www-form-urlencoded",
            **(auth if auth is not None else self.credentials()),
        )

    def exchange(self, code, verifier, *, redirect_uri=REDIRECT_URI, auth=None, **extra):
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            **extra,
        }
        return self.form(TOKEN_URL, body, auth)

    def refresh(self, refresh_token, *, auth=None):
        return self.form(TOKEN_URL, {"grant_type": "refresh_token", "refresh_token": refresh_token}, auth)

    def revoke(self, token, *, auth=None):
        return self.form(REVOKE_URL, {"token": token}, auth)

    # --- what the person does in their browser --------------------------------

    @staticmethod
    def browser(user):
        browser = APIClient()
        browser.force_login(user)
        return browser

    @staticmethod
    def request_token_from(response):
        return response.json()["authorization_url"].rsplit("/", 1)[1]

    def consent(self, user, link_token):
        return self.browser(user).get(f"/api/agent/connect/{link_token}/")

    def decide(self, user, link_token, nonce, *, action="approve", origin=OWN_ORIGIN, content_type="json"):
        extra = {} if origin is None else {"HTTP_ORIGIN": origin}
        kwargs = {"format": "json"} if content_type == "json" else {}
        return self.browser(user).post(
            f"/api/agent/connect/{link_token}/{action}/", {"nonce": nonce}, **kwargs, **extra
        )

    def code_from(self, response):
        query = parse_qs(urlsplit(response.json()["redirect_to"]).query)
        return query["code"][0]

    # --- the whole thing ------------------------------------------------------

    def link(self, user, *, scope=ALL_SCOPES, **overrides):
        """Link a person end to end. Returns the token response body."""
        response, verifier = self.link_request(scope=scope, **overrides)
        assert response.status_code == 201, response.content
        link_token = self.request_token_from(response)
        nonce = self.consent(user, link_token).json()["nonce"]
        approved = self.decide(user, link_token, nonce)
        assert approved.status_code == 200, approved.content
        exchanged = self.exchange(self.code_from(approved), verifier)
        assert exchanged.status_code == 200, exchanged.content
        return exchanged.json()


def bearer(access_token):
    http = APIClient()
    http.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return http


@pytest.fixture(autouse=True)
def private_throttle_cache(monkeypatch):
    """Give every test its own rate-limit counters.

    The real ones live in the shared cache and outlive the test database, so a fast
    run would spend one bucket across hundreds of tests and see 429s that mean
    nothing. A test that is about the limit sets a tiny one of its own.
    """
    from django.core.cache.backends.locmem import LocMemCache

    from plane.agent.throttles import ClientRateThrottle, ConsentRateThrottle, GrantRateThrottle, OAuthRateThrottle

    cache = LocMemCache(f"agent-throttle-{uuid4().hex}", {})
    for throttle in (GrantRateThrottle, ClientRateThrottle, OAuthRateThrottle, ConsentRateThrottle):
        monkeypatch.setattr(throttle, "cache", cache)


@pytest.fixture
def make_app(db):
    def _make(**fields):
        secret = "plane_cs_" + secrets.token_urlsafe(32)
        client = AgentClient.objects.create(
            client_id=f"plane_client_{uuid4().hex[:24]}",
            name=fields.pop("name", "Test bot"),
            secret_hash=hash_secret(secret),
            redirect_uris=fields.pop("redirect_uris", [REDIRECT_URI]),
            allowed_scopes=fields.pop("allowed_scopes", list(SCOPES)),
            **fields,
        )
        return BotApp(client, secret)

    return _make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def person(db):
    """A signed-in-able member of the company who will link the bot."""
    from plane.tests.factories import UserFactory

    return UserFactory(first_name="Pat", last_name="Person")


@pytest.fixture
def linked(app, person):
    """The person, linked to the app: the token response body."""
    return app.link(person)
