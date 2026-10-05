# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Unit tests for SessionRenewalMiddleware: the sessions it has to leave alone.

What it does for a session in use is covered end to end in
contract/app/test_session_renewal.py. These are the guards that are awkward to
reach from there, and none of them is allowed to touch the database.
"""

from unittest.mock import Mock

import pytest
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from plane.authentication.middleware.session_renewal import RENEWED_AT, SessionRenewalMiddleware
from plane.db.models.session import SessionStore


def signed_in_request():
    """A request whose session was loaded for someone signed in, and not changed since."""
    request = RequestFactory().get("/api/users/me/")
    request.session = SessionStore()
    request.session[SESSION_KEY] = "1"
    request.session.modified = False
    request.user = Mock(is_authenticated=True)
    return request


def respond_to(request):
    response = HttpResponse()
    assert SessionRenewalMiddleware(Mock()).process_response(request, response) is response
    return request


@pytest.mark.unit
class TestSessionRenewalMiddleware:
    def test_a_session_in_use_is_marked_to_be_saved(self):
        request = respond_to(signed_in_request())

        assert request.session.modified
        assert isinstance(request.session[RENEWED_AT], int)

    def test_a_record_of_renewal_that_cannot_be_read_counts_as_none(self):
        request = signed_in_request()
        request.session[RENEWED_AT] = "yesterday"
        request.session.modified = False

        respond_to(request)

        assert isinstance(request.session[RENEWED_AT], int)

    def test_a_session_with_an_expiry_of_its_own_keeps_it(self):
        request = signed_in_request()
        request.session.set_expiry(settings.ADMIN_SESSION_COOKIE_AGE)
        request.session.modified = False

        respond_to(request)

        assert not request.session.modified

    def test_a_session_is_not_started_for_a_request_authenticated_some_other_way(self):
        # An API key authenticates the request, and something looked at the
        # empty session on the way.
        request = signed_in_request()
        del request.session[SESSION_KEY]
        request.session.modified = False

        respond_to(request)

        assert not request.session.modified
        assert request.session.is_empty()

    def test_someone_who_may_no_longer_sign_in_is_not_kept_signed_in(self):
        request = signed_in_request()
        request.user = AnonymousUser()

        respond_to(request)

        assert not request.session.modified

    def test_a_session_the_request_never_loaded_is_not_read(self):
        request = RequestFactory().get("/api/users/me/")
        request.session = SessionStore(session_key="never-loaded")
        request.user = Mock(is_authenticated=True)

        respond_to(request)

        assert not request.session.accessed

    def test_a_request_answered_before_it_was_authenticated_passes_through(self):
        request = signed_in_request()
        del request.user

        respond_to(request)

        assert not request.session.modified

    def test_a_request_without_a_session_passes_through(self):
        respond_to(RequestFactory().get("/"))
