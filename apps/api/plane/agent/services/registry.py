# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Registering and changing the apps that may be connected, for whoever is allowed to decide that.

Two doors lead here and must behave the same: the `agent_client` command, for whoever runs
the server, and the instance administrators' screen in the admin app. Both call these
functions, so a rule (what an address may look like, what a new app is allowed to ask for)
is written once. Every function raises `RegistryError` with a sentence the person making the
change can read, and none of them knows about HTTP or the command line.

The client secret is shown once, when it is made or replaced, and only its hash is kept.
The events signing secret is not stored either (see `events.webhook_secret`), so it can be
shown again to somebody who is allowed to see it.
"""

# Django imports
from django.utils import timezone

# Module imports
from plane.agent import oauth
from plane.agent.models import AgentClient, AgentGrant
from plane.agent.scopes import DEFAULT_SCOPES, unknown_scopes
from plane.agent.services import events
from plane.agent.tokens import CLIENT_ID_PREFIX, CLIENT_SECRET_PREFIX, hash_secret, new_secret

MAX_NAME = 120
MAX_DESCRIPTION = 1000
# The column that holds an address in a link request is 2048 characters long.
MAX_REDIRECT_URI = 2000
MAX_REDIRECT_URIS = 10


class RegistryError(ValueError):
    """A change that cannot be made. The message says why, for the person who asked for it."""


def clean_name(value):
    name = value.strip() if isinstance(value, str) else ""
    if not name:
        raise RegistryError("An app needs a name.")
    if len(name) > MAX_NAME:
        raise RegistryError(f"The name must be at most {MAX_NAME} characters.")
    return name


def clean_description(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RegistryError("The description must be text.")
    description = value.strip()
    if len(description) > MAX_DESCRIPTION:
        raise RegistryError(f"The description must be at most {MAX_DESCRIPTION} characters.")
    return description


def clean_redirect_uris(value):
    """The addresses people may be sent back to: at least one, each valid, without repeats."""
    if not isinstance(value, (list, tuple)) or not all(isinstance(uri, str) for uri in value):
        raise RegistryError("The redirect addresses must be a list of addresses.")
    uris = list(dict.fromkeys(uri.strip() for uri in value if uri.strip()))
    if not uris:
        raise RegistryError("An app needs at least one redirect address.")
    if len(uris) > MAX_REDIRECT_URIS:
        raise RegistryError(f"An app may have at most {MAX_REDIRECT_URIS} redirect addresses.")
    for uri in uris:
        if len(uri) > MAX_REDIRECT_URI:
            raise RegistryError(f"The redirect address {uri[:60]!r}… is too long.")
        problem = oauth.validate_redirect_uri(uri)
        if problem:
            raise RegistryError(f"The redirect address {uri!r} {problem}.")
    return uris


def clean_scopes(value):
    if not isinstance(value, (list, tuple)) or not all(isinstance(scope, str) for scope in value):
        raise RegistryError("The scopes must be a list of scope names.")
    scopes = list(dict.fromkeys(value))
    if not scopes:
        raise RegistryError("An app needs at least one scope.")
    if unknown_scopes(scopes):
        raise RegistryError(f"Unknown scope(s): {', '.join(unknown_scopes(scopes))}.")
    return scopes


def find(client_id):
    client = AgentClient.objects.filter(client_id=client_id).first()
    if client is None:
        raise RegistryError(f"No app with id {client_id}.")
    return client


def create_client(*, name, description="", redirect_uris, scopes=None):
    """Register an app. Returns the client and its secret, which is not kept anywhere else.

    An app that names no scopes gets the ones that only read the linking person's own
    information. Being allowed to change people's work, or to see their colleagues', is a
    decision somebody makes on purpose, not a default.
    """
    name = clean_name(name)
    description = clean_description(description)
    redirect_uris = clean_redirect_uris(redirect_uris)
    scopes = clean_scopes(scopes) if scopes else list(DEFAULT_SCOPES)
    secret = new_secret(CLIENT_SECRET_PREFIX)
    client = AgentClient.objects.create(
        client_id=new_secret(CLIENT_ID_PREFIX)[: len(CLIENT_ID_PREFIX) + 24],
        name=name,
        description=description,
        secret_hash=hash_secret(secret),
        redirect_uris=redirect_uris,
        allowed_scopes=scopes,
    )
    return client, secret


def update_client(client, *, name=None, description=None, redirect_uris=None, allowed_scopes=None, is_active=None):
    """Change what was named; leave the rest. Returns the names of the fields that really changed.

    A form that is saved as it was changes nothing and says so, so the audit log only ever
    records changes. Connections that already exist keep the scopes they were given: narrowing
    what an app *may* ask for does not reach back into what people have already agreed to.
    Ending those is a separate act (`revoke_grants`).
    """
    wanted = {}
    if name is not None:
        wanted["name"] = clean_name(name)
    if description is not None:
        wanted["description"] = clean_description(description)
    if redirect_uris is not None:
        wanted["redirect_uris"] = clean_redirect_uris(redirect_uris)
    if allowed_scopes is not None:
        wanted["allowed_scopes"] = clean_scopes(allowed_scopes)
    if is_active is not None:
        if not isinstance(is_active, bool):
            raise RegistryError("is_active must be true or false.")
        wanted["is_active"] = is_active
    # Nothing is changed before everything has been checked, so a bad value changes nothing at all.
    changed = [field for field, value in wanted.items() if getattr(client, field) != value]
    for field in changed:
        setattr(client, field, wanted[field])
    if changed:
        client.save(update_fields=[*changed, "updated_at"])
    return changed


def rotate_secret(client):
    """Make a new secret. The old one stops working at once. Returns the new one, shown only now."""
    secret = new_secret(CLIENT_SECRET_PREFIX)
    client.secret_hash = hash_secret(secret)
    client.secret_rotated_at = timezone.now()
    client.save(update_fields=["secret_hash", "secret_rotated_at", "updated_at"])
    return secret


def set_webhook(client, *, url=None, off=False, new_secret=False):
    """Say where the app is told about events, switch that off, or change the signing secret.

    Setting an address switches delivery back on, which is how an app that was given up on
    after repeated failures is restored. Returns whether anything changed.
    """
    if url and off:
        raise RegistryError("Give either an address or off, not both.")
    changed = False
    if off:
        client.webhook_url, client.webhook_failures, client.webhook_disabled_at = "", 0, None
        changed = True
    elif url:
        try:
            client.webhook_url = events.check_webhook_url(url)
        except ValueError as error:
            raise RegistryError(str(error))
        client.webhook_failures, client.webhook_disabled_at = 0, None
        changed = True
    if new_secret:
        client.webhook_secret_version += 1
        changed = True
    if changed:
        client.save(
            update_fields=[
                "webhook_url",
                "webhook_secret_version",
                "webhook_failures",
                "webhook_disabled_at",
                "updated_at",
            ]
        )
    return changed


def live_grants(client):
    return AgentGrant.objects.filter(client=client, revoked_at__isnull=True)


def revoke_grants(client, *, email=None, grant_id=None, request=None):
    """End the app's connections: all of them, one person's, or one. Returns how many were ended."""
    grants = live_grants(client).select_related("user", "client")
    if email:
        grants = grants.filter(user__email__iexact=email)
    if grant_id:
        grants = grants.filter(id=grant_id)
    count = 0
    for grant in grants:
        oauth.revoke_grant(grant, oauth.BY_ADMIN, request=request)
        count += 1
    return count
