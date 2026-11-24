# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Linking a person to an app, and keeping that link safe.

This follows OAuth 2.0 (RFC 6749) with three of its hardening extensions, so that a
client library written for OAuth works against it unchanged:

* The app registers its request first, from its own server, and the person is sent
  a link naming that request (pushed authorization requests, RFC 9126). Nothing the
  person's browser carries can be altered on the way: not the scopes, not the
  address they are sent back to, not the account the app says it is linking.
* The code that comes back is only any use together with a secret the app made up
  for that one request (PKCE, RFC 7636, `S256` only), so a code read off a screen
  or out of a log cannot be spent by anybody else.
* A refresh token works once. Presenting a spent one a second time means somebody
  copied it, and ends the link (OAuth 2.0 Security Best Current Practice).

What is *not* here is a login screen. The person is already signed in to Plane in
their browser, and that is the only place they ever type anything.
"""

# Python imports
import base64
import hashlib
import hmac
import re
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit

# Django imports
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

# Module imports
from plane.agent import audit, conf
from plane.agent.errors import AgentError, invalid_client, invalid_grant, invalid_request
from plane.agent.models import AgentAuthorizationRequest, AgentClient, AgentGrant, AgentToken
from plane.agent.scopes import parse_scope_string, unknown_scopes
from plane.agent.services import events
from plane.agent.text import clean_display_text
from plane.agent.tokens import (
    ACCESS_PREFIX,
    CODE_PREFIX,
    REFRESH_PREFIX,
    REQUEST_PREFIX,
    hash_secret,
    new_secret,
    secrets_match,
)
from plane.utils.exception_logger import log_exception

CODE_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")
CODE_VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
PROVIDER = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

CONSENT_SALT = "plane.agent.consent"

# Revocation reasons, recorded on the grant.
BY_USER = "user"
BY_CLIENT = "client"
BY_ADMIN = "admin"
CODE_REUSED = "code_reuse"
TOKEN_REUSED = "token_reuse"
SUPERSEDED = "superseded"


# --- Clients -----------------------------------------------------------------


def authenticate_client(request, params):
    """The client a request comes from, proved by its secret.

    The secret travels in an `Authorization: Basic` header or in the body, never in
    the address: the address is written to every log between here and the app.
    """
    client_id = secret = None
    header = request.headers.get("Authorization", "")
    if header[:6].lower() == "basic ":
        try:
            decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
            client_id, _, secret = decoded.partition(":")
            client_id, secret = unquote_plus(client_id), unquote_plus(secret)
        except (ValueError, UnicodeDecodeError):
            raise invalid_client()
    else:
        client_id, secret = params.get("client_id"), params.get("client_secret")

    if not isinstance(client_id, str) or not isinstance(secret, str) or not client_id or not secret:
        raise invalid_client()

    client = AgentClient.objects.filter(client_id=client_id, is_active=True).first()
    # The same work is done whether or not the client exists, so the time taken does
    # not say which client ids are registered.
    stored = client.secret_hash if client else ""
    if not secrets_match(secret, stored) or client is None:
        raise invalid_client()
    return client


def validate_redirect_uri(uri):
    """Whether an address may be registered for a client; returns the reason it may not.

    HTTPS only, with one exception: a loopback address over plain HTTP, for an app
    still being built. No fragment (a browser would drop it, so the app would never
    see what was sent there) and no credentials in the address.
    """
    try:
        parts = urlsplit(uri)
        host = parts.hostname
    except ValueError:
        return "is not a valid address"
    if not host or parts.username or parts.password:
        return "must be an absolute address without credentials"
    if parts.fragment or "#" in uri:
        return "must not contain a fragment"
    if parts.scheme == "https":
        return None
    if parts.scheme == "http" and host in ("localhost", "127.0.0.1", "::1"):
        return None
    return "must use https (plain http is only accepted for localhost)"


# --- The link a person is sent -----------------------------------------------


def _text(params, name, *, required=False, max_length=255):
    value = params.get(name)
    if value is None or value == "":
        if required:
            raise invalid_request(f"{name} is required.")
        return ""
    if not isinstance(value, str):
        raise invalid_request(f"{name} must be a string.")
    if len(value) > max_length * 4:
        raise invalid_request(f"{name} is too long.")
    return value


def connect_url(request_token):
    """Where in the web app the person is sent to say yes."""
    base = (getattr(settings, "WEB_URL", None) or getattr(settings, "APP_BASE_URL", None) or "").rstrip("/")
    if not base:
        raise AgentError("server_error", "The server does not know its own web address (WEB_URL).", status_code=500)
    return f"{base}/connect/agent/{request_token}"


def create_authorization_request(client, params, *, request=None):
    """Register what an app wants to be linked for, and return the link for the person.

    Everything is checked here, before a person is asked anything, so that the
    consent screen only ever shows a request that could be granted.
    """
    redirect_uri = _text(params, "redirect_uri", required=True, max_length=2048)
    if redirect_uri not in (client.redirect_uris or []):
        raise invalid_request("redirect_uri is not one of the addresses registered for this client.")

    scopes = parse_scope_string(_text(params, "scope", required=True, max_length=512))
    if not scopes:
        raise invalid_request("scope is required.")
    if unknown_scopes(scopes):
        raise AgentError("invalid_scope", f"Unknown scope: {', '.join(unknown_scopes(scopes))}.")
    refused = [scope for scope in scopes if scope not in (client.allowed_scopes or [])]
    if refused:
        raise AgentError("invalid_scope", f"This client may not ask for: {', '.join(refused)}.")

    client_state = _text(params, "state", required=True, max_length=512)
    if len(client_state) > 512:
        raise invalid_request("state must be at most 512 characters.")

    if _text(params, "code_challenge_method", required=True, max_length=8) != "S256":
        raise invalid_request("code_challenge_method must be S256.")
    code_challenge = _text(params, "code_challenge", required=True, max_length=128)
    if not CODE_CHALLENGE.match(code_challenge):
        raise invalid_request("code_challenge must be the unpadded base64url SHA-256 of the code verifier.")

    provider = clean_display_text(_text(params, "account_provider", required=True, max_length=32), 32).lower()
    if not PROVIDER.match(provider):
        raise invalid_request("account_provider must be a short lower-case name such as 'telegram'.")
    account_id = clean_display_text(_text(params, "account_id", required=True, max_length=64), 64)
    if not account_id:
        raise invalid_request("account_id is required.")

    token = new_secret(REQUEST_PREFIX)
    row = AgentAuthorizationRequest.objects.create(
        request_hash=hash_secret(token),
        client=client,
        redirect_uri=redirect_uri,
        scopes=scopes,
        client_state=client_state,
        code_challenge=code_challenge,
        account_provider=provider,
        account_id=account_id,
        account_username=clean_display_text(_text(params, "account_username", max_length=64), 64),
        account_name=clean_display_text(_text(params, "account_name", max_length=120), 120),
        expires_at=timezone.now() + conf.REQUEST_LIFETIME,
    )
    audit.record("request", request=request, client=client, request_id=str(row.id), account_provider=provider)
    return row, token


def find_request(request_token):
    """The pending request a link names, or None.

    None for anything that is not a request a person can still act on: unknown,
    already decided, expired, or belonging to a client that has since been switched off.
    """
    if not isinstance(request_token, str) or not request_token.startswith(REQUEST_PREFIX):
        return None
    row = (
        AgentAuthorizationRequest.objects.select_related("client")
        .filter(request_hash=hash_secret(request_token))
        .first()
    )
    if row is None or not row.client.is_active:
        return None
    if row.status != AgentAuthorizationRequest.Status.PENDING or row.expires_at <= timezone.now():
        return None
    return row


def consent_nonce(row, user):
    """What the consent screen must send back to prove it was the one that showed the request.

    Bound to the request and to the person looking at it, so a page on another site
    that tricks a signed-in browser into posting "approve" has nothing to post: it
    cannot read this, because it is only ever in the response to a request that site
    is not allowed to read.
    """
    return signing.dumps({"r": str(row.id), "u": str(user.id)}, salt=CONSENT_SALT)


def _nonce_matches(row, user, nonce):
    try:
        data = signing.loads(nonce, salt=CONSENT_SALT, max_age=int(conf.REQUEST_LIFETIME.total_seconds()))
    except signing.BadSignature:
        return False
    return hmac.compare_digest(str(data.get("r")), str(row.id)) and hmac.compare_digest(
        str(data.get("u")), str(user.id)
    )


def _redirect(uri, **params):
    parts = urlsplit(uri)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query += [(key, value) for key, value in params.items() if value is not None]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _lock_request(row_id):
    # Only the request's own row is locked, not the client's and not the person's.
    return AgentAuthorizationRequest.objects.select_for_update(of=("self",)).select_related("client").get(pk=row_id)


def approve(row, user, nonce, *, request=None):
    """The person said yes. Returns the address to send them to, carrying the code."""
    if not user.is_active or user.is_bot:
        raise AgentError("access_denied", "This account cannot connect apps.", status_code=403)
    if not isinstance(nonce, str) or not _nonce_matches(row, user, nonce):
        raise AgentError("invalid_request", "The confirmation is not valid. Reload the page and try again.")

    with transaction.atomic():
        locked = _lock_request(row.id)
        now = timezone.now()
        if (
            locked.status != AgentAuthorizationRequest.Status.PENDING
            or locked.expires_at <= now
            or not locked.client.is_active
        ):
            raise AgentError("invalid_request", "This link has expired or has already been used.")
        code = new_secret(CODE_PREFIX)
        locked.status = AgentAuthorizationRequest.Status.APPROVED
        locked.user = user
        locked.decided_at = now
        locked.code_hash = hash_secret(code)
        locked.code_expires_at = now + conf.CODE_LIFETIME
        locked.save(update_fields=["status", "user", "decided_at", "code_hash", "code_expires_at"])
    audit.record("approved", request=request, client=locked.client, user=user, request_id=str(locked.id))
    return _redirect(locked.redirect_uri, code=code, state=locked.client_state)


def deny(row, user, nonce, *, request=None):
    """The person said no. Returns the address to send them to, carrying the refusal."""
    if not isinstance(nonce, str) or not _nonce_matches(row, user, nonce):
        raise AgentError("invalid_request", "The confirmation is not valid. Reload the page and try again.")
    with transaction.atomic():
        locked = _lock_request(row.id)
        if locked.status != AgentAuthorizationRequest.Status.PENDING:
            raise AgentError("invalid_request", "This link has expired or has already been used.")
        locked.status = AgentAuthorizationRequest.Status.DENIED
        locked.user = user
        locked.decided_at = timezone.now()
        locked.save(update_fields=["status", "user", "decided_at"])
    audit.record("denied", request=request, client=locked.client, user=user, request_id=str(locked.id))
    return _redirect(locked.redirect_uri, error="access_denied", state=locked.client_state)


# --- Tokens ------------------------------------------------------------------


def _pkce_matches(verifier, challenge):
    if not isinstance(verifier, str) or not CODE_VERIFIER.match(verifier):
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(computed, challenge)


def _issue_tokens(grant, now):
    """A new access token and refresh token under a grant. The only place they exist in the clear."""
    limit = grant.expires_at
    access_expires = now + conf.ACCESS_TOKEN_LIFETIME
    refresh_expires = now + conf.REFRESH_TOKEN_LIFETIME
    if limit is not None:
        access_expires, refresh_expires = min(access_expires, limit), min(refresh_expires, limit)
    access, refresh = new_secret(ACCESS_PREFIX), new_secret(REFRESH_PREFIX)
    AgentToken.objects.bulk_create(
        [
            AgentToken(
                grant=grant,
                kind=AgentToken.ACCESS,
                token_hash=hash_secret(access),
                created_at=now,
                expires_at=access_expires,
            ),
            AgentToken(
                grant=grant,
                kind=AgentToken.REFRESH,
                token_hash=hash_secret(refresh),
                created_at=now,
                expires_at=refresh_expires,
            ),
        ]
    )
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": int((access_expires - now).total_seconds()),
        "refresh_token": refresh,
        "scope": " ".join(grant.scopes),
    }


def exchange_code(client, params, *, request=None):
    """Spend the code from an approval and return the first pair of tokens."""
    code = _text(params, "code", required=True, max_length=255)
    if _text(params, "grant_type", max_length=32) != "authorization_code":
        raise AgentError("unsupported_grant_type", "grant_type must be authorization_code or refresh_token.")

    redirect_uri = _text(params, "redirect_uri", required=True, max_length=2048)

    grant = result = reused_grant = None
    superseded = []
    failure = ""
    with transaction.atomic():
        row = (
            AgentAuthorizationRequest.objects.select_for_update(of=("self",))
            .select_related("user")
            .filter(code_hash=hash_secret(code), client=client)
            .first()
        )
        if row is None:
            raise invalid_grant()
        now = timezone.now()
        if row.status == AgentAuthorizationRequest.Status.EXCHANGED:
            reused_grant = row.grant
        elif (
            row.status != AgentAuthorizationRequest.Status.APPROVED
            or row.code_expires_at is None
            or row.code_expires_at <= now
        ):
            failure = "The code has expired or has already been used."
        elif redirect_uri != row.redirect_uri or not _pkce_matches(params.get("code_verifier"), row.code_challenge):
            # Whoever presented the code does not hold what only the app that asked
            # for it was given. The code is spent, so that guessing cannot go on.
            row.status = AgentAuthorizationRequest.Status.DENIED
            row.save(update_fields=["status"])
            failure = "redirect_uri or code_verifier does not match the request the code was issued for."
        elif row.user is None or not row.user.is_active:
            failure = "The account that approved this link is no longer active."
        else:
            # Linking the same chat account again replaces the earlier connection, so the old
            # tokens (a refresh token is good for months) do not pile up unused.
            superseded = list(
                AgentGrant.objects.filter(
                    user=row.user,
                    client=client,
                    account_provider=row.account_provider,
                    account_id=row.account_id,
                    revoked_at__isnull=True,
                )
            )
            grant = AgentGrant.objects.create(
                user=row.user,
                client=client,
                scopes=row.scopes,
                account_provider=row.account_provider,
                account_id=row.account_id,
                account_username=row.account_username,
                account_name=row.account_name,
                created_at=now,
                expires_at=(now + conf.GRANT_MAX_AGE) if conf.GRANT_MAX_AGE else None,
            )
            row.status = AgentAuthorizationRequest.Status.EXCHANGED
            row.grant = grant
            row.save(update_fields=["status", "grant"])
            result = _issue_tokens(grant, now)

    # Raised out here, after the transaction has committed, so that what was done
    # above (a code spent, a connection ended) is kept even though the call fails.
    if reused_grant is not None:
        revoke_grant(reused_grant, CODE_REUSED, request=request)
        raise invalid_grant("The code has already been used. The connection it created has been ended.")
    if failure:
        raise invalid_grant(failure)

    for earlier in superseded:
        revoke_grant(earlier, SUPERSEDED, request=request)
    audit.record("linked", request=request, client=client, grant=grant)
    return result


def refresh(client, params, *, request=None):
    """Replace a refresh token with a new pair. The old one works once."""
    if _text(params, "grant_type", max_length=32) != "refresh_token":
        raise AgentError("unsupported_grant_type", "grant_type must be authorization_code or refresh_token.")
    presented = _text(params, "refresh_token", required=True, max_length=255)

    copied_grant = None
    result = None
    retried = False
    with transaction.atomic():
        token = (
            AgentToken.objects.select_for_update(of=("self",))
            .select_related("grant", "grant__user", "grant__client")
            .filter(token_hash=hash_secret(presented), kind=AgentToken.REFRESH)
            .first()
        )
        if token is None or token.grant.client_id != client.id:
            raise invalid_grant()
        now = timezone.now()
        grant = token.grant
        if token.revoked_at is not None or token.expires_at <= now or not grant.is_usable(now):
            raise invalid_grant("The refresh token has expired or been revoked. The person has to link again.")
        if not grant.user.is_active:
            raise invalid_grant("The account this connection belongs to is no longer active.")
        if token.used_at is not None:
            if now - token.used_at > conf.REFRESH_REUSE_LEEWAY:
                copied_grant = grant
            else:
                # An app that asked twice at once, or retried after a lost reply.
                retried = True
        if copied_grant is None:
            if token.used_at is None:
                token.used_at = now
                token.save(update_fields=["used_at"])
            result = _issue_tokens(grant, now)

    if copied_grant is not None:
        revoke_grant(copied_grant, TOKEN_REUSED, request=request)
        audit.record("reuse_detected", request=request, client=client, grant=copied_grant)
        raise invalid_grant("The refresh token was already used. The connection has been ended.")

    audit.record("refresh_retry" if retried else "refreshed", request=request, client=client, grant=grant)
    return result


def revoke_grant(grant, reason, *, request=None):
    """End a link and every token under it, at once."""
    now = timezone.now()
    newly_ended = False
    with transaction.atomic():
        if grant.revoked_at is None:
            grant.revoked_at = now
            grant.revoked_reason = reason
            grant.save(update_fields=["revoked_at", "revoked_reason"])
            newly_ended = True
        grant.tokens.filter(revoked_at__isnull=True).update(revoked_at=now)
    audit.record("revoked", request=request, grant=grant, reason=reason)
    if newly_ended:
        _announce_ended(grant, reason)


def _announce_ended(grant, reason):
    """Tell the app its link was ended by somebody else, so it can forget the tokens. Never fails the revoke."""
    try:
        events.announce_revoked(grant, reason)
    except Exception as error:  # noqa: BLE001 - ending access must not depend on telling anybody
        log_exception(error)


def revoke_token(client, params, *, request=None):
    """RFC 7009: the app says it has no further use for a token. Unknown tokens are not an error."""
    presented = _text(params, "token", required=True, max_length=255)
    token = (
        AgentToken.objects.select_related("grant", "grant__client")
        .filter(token_hash=hash_secret(presented), grant__client=client)
        .first()
    )
    if token is None:
        return
    if token.kind == AgentToken.REFRESH:
        revoke_grant(token.grant, BY_CLIENT, request=request)
    elif token.revoked_at is None:
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
