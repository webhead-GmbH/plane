# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Making and checking the secrets connected apps hold.

Every secret here is 256 bits from the system's random source, so there is nothing
to guess and nothing for a slow password hash to protect: a plain SHA-256 is enough
to keep a copy of the database from being a copy of everybody's access. What is
stored is the hash; the secret itself is shown once and never again.

The prefixes are not for security. They make a leaked value recognisable: a secret
scanner can be taught `plane_at_`, and a person who finds one in a log can tell what
it is.
"""

# Python imports
import hashlib
import hmac
import secrets

CLIENT_ID_PREFIX = "plane_client_"
CLIENT_SECRET_PREFIX = "plane_cs_"
REQUEST_PREFIX = "plane_ar_"
CODE_PREFIX = "plane_ac_"
ACCESS_PREFIX = "plane_at_"
REFRESH_PREFIX = "plane_rt_"


def new_secret(prefix):
    return prefix + secrets.token_urlsafe(32)


def hash_secret(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def secrets_match(value, stored_hash):
    """Whether a presented secret is the one whose hash is stored, in constant time."""
    return hmac.compare_digest(hash_secret(value), stored_hash or "")
