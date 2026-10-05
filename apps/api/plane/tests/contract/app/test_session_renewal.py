# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
A session lasts for as long as it is used.

People used to be signed out a fixed time after signing in, however recently
they had used Plane. These tests go through the whole middleware stack, so they
also hold SessionRenewalMiddleware to its place in MIDDLEWARE: in the wrong
place it would mark a session after the session middleware had already decided
not to save it.
"""

import time
from datetime import timedelta
from uuid import uuid4

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework import status

from plane.authentication.middleware.session_renewal import RENEWED_AT
from plane.db.models.session import Session, SessionStore
from plane.license.models import Instance, InstanceAdmin

ME = "/api/users/me/"
A_MINUTE = timedelta(minutes=1)


@pytest.fixture
def signed_in(api_client, create_user):
    """A browser signed in with a real session, the way the web app is."""
    api_client.force_login(create_user)
    return api_client


def session_key(client):
    return client.cookies[settings.SESSION_COOKIE_NAME].value


def stored(client):
    return Session.objects.get(session_key=session_key(client))


def a_full_lifetime_from_now():
    return timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE)


def last_renewed(client, ago):
    """Put the session where it would be this long after its last renewal."""
    store = SessionStore(session_key=session_key(client))
    store[RENEWED_AT] = int(time.time() - ago.total_seconds())
    store.save()
    Session.objects.filter(session_key=store.session_key).update(expire_date=a_full_lifetime_from_now() - ago)


@pytest.mark.contract
@pytest.mark.django_db
class TestASessionInUseIsKeptAlive:
    def test_a_day_after_its_last_renewal_it_gets_a_full_lifetime_again(self, signed_in):
        last_renewed(signed_in, ago=timedelta(days=2))

        response = signed_in.get(ME)

        assert response.status_code == status.HTTP_200_OK
        assert abs(stored(signed_in).expire_date - a_full_lifetime_from_now()) < A_MINUTE
        # The browser's copy has to last as long as the server's.
        assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == settings.SESSION_COOKIE_AGE

    def test_within_a_day_of_its_last_renewal_it_is_left_alone(self, signed_in):
        last_renewed(signed_in, ago=timedelta(hours=1))
        ends = stored(signed_in).expire_date

        response = signed_in.get(ME)

        assert response.status_code == status.HTTP_200_OK
        assert stored(signed_in).expire_date == ends
        assert settings.SESSION_COOKIE_NAME not in response.cookies

    def test_a_session_from_before_sessions_were_renewed_is_renewed_once(self, signed_in):
        # force_login leaves no record of a renewal, like a session that was
        # signed in before this existed.
        Session.objects.filter(session_key=session_key(signed_in)).update(
            expire_date=timezone.now() + timedelta(days=3)
        )

        first = signed_in.get(ME)
        second = signed_in.get(ME)

        assert abs(stored(signed_in).expire_date - a_full_lifetime_from_now()) < A_MINUTE
        assert settings.SESSION_COOKIE_NAME in first.cookies
        assert settings.SESSION_COOKIE_NAME not in second.cookies

    def test_with_the_interval_at_the_lifetime_a_session_ends_a_fixed_time_after_sign_in(self, signed_in, settings):
        settings.SESSION_RENEWAL_INTERVAL = settings.SESSION_COOKIE_AGE
        last_renewed(signed_in, ago=timedelta(days=2))
        ends = stored(signed_in).expire_date

        response = signed_in.get(ME)

        assert response.status_code == status.HTTP_200_OK
        assert stored(signed_in).expire_date == ends


@pytest.mark.contract
@pytest.mark.django_db
class TestOnlyASignedInSessionIsRenewed:
    def test_someone_who_was_deactivated_is_not_kept_signed_in(self, signed_in, create_user):
        last_renewed(signed_in, ago=timedelta(days=2))
        ends = stored(signed_in).expire_date
        create_user.is_active = False
        create_user.save()

        response = signed_in.get(ME)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert stored(signed_in).expire_date == ends

    def test_a_visitor_is_not_given_a_session(self, api_client):
        response = api_client.get(ME)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert settings.SESSION_COOKIE_NAME not in response.cookies
        assert not Session.objects.exists()

    def test_a_request_made_with_an_api_key_is_not_given_a_session(self, api_key_client):
        response = api_key_client.get("/api/v1/users/me/")

        assert response.status_code == status.HTTP_200_OK
        assert settings.SESSION_COOKIE_NAME not in response.cookies
        assert not Session.objects.exists()

    def test_the_instance_admin_session_keeps_its_short_life(self, api_client, create_user):
        instance = Instance.objects.create(
            instance_name="test",
            instance_id=uuid4().hex,
            current_version="1.0.0",
            last_checked_at=timezone.now(),
        )
        InstanceAdmin.objects.create(instance=instance, user=create_user)
        # Signed in to god-mode: a cookie of its own, and a session that was
        # given an hour.
        api_client.force_login(create_user)
        key = api_client.cookies.pop(settings.SESSION_COOKIE_NAME).value
        api_client.cookies[settings.ADMIN_SESSION_COOKIE_NAME] = key
        store = SessionStore(session_key=key)
        store.set_expiry(settings.ADMIN_SESSION_COOKIE_AGE)
        store.save()
        ends = Session.objects.get(session_key=key).expire_date

        response = api_client.get("/api/instances/admins/me/")

        assert response.status_code == status.HTTP_200_OK
        assert Session.objects.get(session_key=key).expire_date == ends
        assert settings.ADMIN_SESSION_COOKIE_NAME not in response.cookies
