# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Which address a call really came from, for the rate limits and the audit log.

`X-Forwarded-For` is written by every proxy on the way *and* by the caller, so its
first entry — the one a naive reader takes — is whatever the caller chose to claim.
Used for a rate limit, that lets anybody get a fresh allowance by varying a header.
The only entry that can be trusted is the one the nearest of *our* proxies wrote,
which is counted from the end: that is what `NUM_PROXIES` says how to find.

Without `NUM_PROXIES` nothing in the header can be trusted, so the address of the
connection itself is used. Behind a proxy that is the proxy, and all callers then
share one allowance; that is the safe way to be wrong, and the operations guide says
to set `NUM_PROXIES`.
"""

# Python imports
import ipaddress

# Third-party imports
from rest_framework.settings import api_settings


def client_address(request):
    """The caller's IP address as text, or None when it cannot be determined."""
    meta = request.META
    remote = meta.get("REMOTE_ADDR")
    forwarded = meta.get("HTTP_X_FORWARDED_FOR")
    proxies = api_settings.NUM_PROXIES

    candidate = remote
    if proxies and forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            candidate = hops[-min(proxies, len(hops))]

    try:
        return str(ipaddress.ip_address(candidate))
    except (TypeError, ValueError):
        return None
