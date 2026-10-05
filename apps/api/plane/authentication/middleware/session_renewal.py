# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import time

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.utils.deprecation import MiddlewareMixin

# Session key: when the session was last given a full lifetime, in seconds since the epoch.
RENEWED_AT = "renewed_at"


class SessionRenewalMiddleware(MiddlewareMixin):
    """
    Keeps a session alive for as long as it is being used.

    A session otherwise ends SESSION_COOKIE_AGE after sign-in, however recently
    it was used, which signs people out in the middle of their work. Once a
    session has gone SESSION_RENEWAL_INTERVAL without being renewed, the next
    request made with it marks it as modified here, and the session middleware
    then saves it and reissues its cookie, both with a full lifetime. Saving on
    every request (SESSION_SAVE_EVERY_REQUEST) would do the same at the cost of
    a write per request.

    Goes after the session and authentication middleware in MIDDLEWARE: it reads
    request.user, and has to see the response before the session middleware does.
    """

    def process_response(self, request, response):
        if self.is_due(request):
            request.session[RENEWED_AT] = int(time.time())
        return response

    @staticmethod
    def is_due(request):
        session = getattr(request, "session", None)
        # Only a session the request has already loaded: renewing is never the
        # reason one is read from the database.
        if session is None or not session.accessed:
            return False
        # Someone is signed in on it, and is still allowed to be.
        if session.get(SESSION_KEY) is None:
            return False
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        # A session with an expiry of its own keeps it: the instance admin's is
        # short on purpose.
        if session.get("_session_expiry") is not None:
            return False
        renewed_at = session.get(RENEWED_AT)
        if not isinstance(renewed_at, int):
            return True
        return time.time() - renewed_at >= settings.SESSION_RENEWAL_INTERVAL
