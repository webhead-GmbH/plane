# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Apps that act for a person in Plane, and what each has been allowed to do.

Four kinds of row, and the split between them is the security model:

* an `AgentClient` is an application the company has registered (a chat bot, say).
  It proves who it is with a secret and may only ever be sent back to the addresses
  it was registered with.
* an `AgentGrant` is one person's yes to one client, for the scopes that were shown
  to them. It is the thing a person sees under "Connected apps" and the thing they
  revoke. Ending it ends every token under it at once.
* an `AgentToken` is a short-lived access token or a refresh token under a grant.
  Only a hash is stored, so a copy of the database holds nothing that can be used.
* an `AgentAuthorizationRequest` is the link the app asked for on a person's behalf,
  from the moment it is created to the moment its code is spent.

These tables deliberately do not use the soft-delete base the rest of the product
does. A revoked grant stays a row with `revoked_at` set, because "who had access and
when it ended" is the question an audit asks; and nothing here should reappear if
somebody restores a deleted row.
"""

# Python imports
import uuid

# Django imports
from django.conf import settings
from django.db import models
from django.utils import timezone


class AgentClient(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    # Public, and sent with every request. Not a secret.
    client_id = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    # SHA-256 of the secret. The secret is long and random, so it needs no slow hash,
    # and it is shown once, when it is made.
    secret_hash = models.CharField(max_length=64)
    secret_rotated_at = models.DateTimeField(null=True, blank=True)
    # Exact addresses a person may be sent back to. Compared as strings, never as
    # prefixes or patterns: a prefix match is how an approval gets sent to an
    # address the registrant did not mean.
    redirect_uris = models.JSONField(default=list)
    # The most this client may ever ask for.
    allowed_scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    # Where Plane tells the app that something happened (see `services/events.py`). Set by an
    # administrator, never by the app: an address the app could change is an address a stolen
    # secret could point anywhere. Empty means the app polls instead.
    webhook_url = models.URLField(max_length=1024, blank=True, default="")
    # The signing secret is not stored: it is derived from the server's secret key, this
    # client and this number, so a copy of the database holds nothing to forge a delivery
    # with. Raising the number is how it is changed.
    webhook_secret_version = models.PositiveIntegerField(default=1)
    # Events in a row that could not be delivered at all. At the limit the address is switched
    # off, so a dead app is not retried for ever.
    webhook_failures = models.PositiveIntegerField(default=0)
    webhook_disabled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_clients"
        verbose_name = "Agent client"
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.client_id})"


class AgentGrant(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_grants")
    client = models.ForeignKey(AgentClient, on_delete=models.CASCADE, related_name="grants")
    scopes = models.JSONField(default=list)
    # Who, on the app's side, the person linked. Shown back to them under "Connected
    # apps" so they can tell two links of the same app apart, and so a link they do
    # not recognise stands out. These come from the app and are never trusted.
    account_provider = models.CharField(max_length=32, blank=True, default="")
    account_id = models.CharField(max_length=64, blank=True, default="")
    account_username = models.CharField(max_length=64, blank=True, default="")
    account_name = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # user, client, admin, code_reuse, token_reuse, expired_user
    revoked_reason = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        db_table = "agent_grants"
        verbose_name = "Agent grant"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "revoked_at"], name="agent_grant_user_live")]

    def __str__(self):
        return f"{self.client_id} for {self.user_id}"

    def is_usable(self, now=None):
        now = now or timezone.now()
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)


class AgentToken(models.Model):
    ACCESS = "access"
    REFRESH = "refresh"
    KINDS = ((ACCESS, "Access"), (REFRESH, "Refresh"))

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    grant = models.ForeignKey(AgentGrant, on_delete=models.CASCADE, related_name="tokens")
    kind = models.CharField(max_length=8, choices=KINDS)
    # SHA-256 of the token. Unique, so it is also how a presented token is found.
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    # A refresh token is spent the first time it is used. A second use means it was
    # copied, and ends the grant.
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_tokens"
        verbose_name = "Agent token"
        indexes = [
            models.Index(fields=["grant", "kind"], name="agent_token_grant_kind"),
            models.Index(fields=["expires_at"], name="agent_token_expires"),
        ]


class AgentAuthorizationRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"
        EXCHANGED = "exchanged", "Exchanged"

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    # SHA-256 of the identifier in the link. The link is the only copy.
    request_hash = models.CharField(max_length=64, unique=True)
    client = models.ForeignKey(AgentClient, on_delete=models.CASCADE, related_name="authorization_requests")
    redirect_uri = models.CharField(max_length=2048)
    scopes = models.JSONField(default=list)
    # The app's `state` parameter, handed back unchanged so it can tell which of its
    # own pending links this was.
    client_state = models.CharField(max_length=512)
    code_challenge = models.CharField(max_length=128)
    account_provider = models.CharField(max_length=32)
    account_id = models.CharField(max_length=64)
    account_username = models.CharField(max_length=64, blank=True, default="")
    account_name = models.CharField(max_length=120, blank=True, default="")

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    # Set on approval, spent on exchange.
    code_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    code_expires_at = models.DateTimeField(null=True, blank=True)
    # The grant a spent code produced, so that a second use of the same code can end it.
    grant = models.ForeignKey(AgentGrant, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        db_table = "agent_authorization_requests"
        verbose_name = "Agent authorization request"
        indexes = [models.Index(fields=["expires_at"], name="agent_request_expires")]


class AgentAuditLog(models.Model):
    """What connected apps did, and what happened to their access.

    Records that something happened and to whom, never what was in it: no query
    strings, no request or response bodies. The log exists so somebody can answer
    "what did this app do for me last week", and a copy of the content would make
    the log itself the thing worth stealing.
    """

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    # request, linked, refreshed, refresh_retry, revoked, reuse_detected, denied
    event = models.CharField(max_length=32)
    client = models.ForeignKey(AgentClient, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    grant = models.ForeignKey(AgentGrant, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    method = models.CharField(max_length=8, blank=True, default="")
    path = models.CharField(max_length=255, blank=True, default="")
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "agent_audit_logs"
        verbose_name = "Agent audit log"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["grant", "-created_at"], name="agent_audit_grant")]


class AgentIdempotencyKey(models.Model):
    """The answer to a write, kept so that asking again with the same key does not do it twice.

    Chat apps retry (a webhook is delivered twice, a model calls a tool again, a network
    drops the reply), and every one of those would otherwise create a second work item, a
    second comment, another hour on somebody's month. The app names each *intended* action
    with a key; the first time, the action is done and its answer is stored here; every
    later time with the same key, the stored answer comes back and nothing is done.
    """

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    grant = models.ForeignKey(AgentGrant, on_delete=models.CASCADE, related_name="+")
    # SHA-256 of the key the app chose; keys are only unique within one connection.
    key_hash = models.CharField(max_length=64)
    # SHA-256 of what was asked. The same key with something different is a mistake in the
    # app, and is refused rather than answered with the wrong thing.
    request_hash = models.CharField(max_length=64)
    # Null while the first request is still being worked on.
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "agent_idempotency_keys"
        verbose_name = "Agent idempotency key"
        constraints = [models.UniqueConstraint(fields=["grant", "key_hash"], name="agent_idempotency_once")]
        indexes = [models.Index(fields=["expires_at"], name="agent_idempotency_expires")]


class AgentEvent(models.Model):
    """Something that happened that one connected person's app may want to hear about.

    The row says *that* it happened and to what, by id: no names, no text, no dates. The app
    fetches the details with the person's own token, which decides again at that moment what
    the person may see. So an event can never carry anything the person could not read, and
    the table holds nothing worth stealing.

    It is also the record of whether the app was told: a delivery is retried until it is
    accepted or given up on, and the outcome is kept for a few days.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    grant = models.ForeignKey(AgentGrant, on_delete=models.CASCADE, related_name="events")
    # work_item.assigned, work_item.unassigned, work_item.due_date_changed, work_item.state_changed,
    # connection.revoked
    event_type = models.CharField(max_length=40)
    # Ids only. What the app receives, apart from the connection details added when it is sent.
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    # What the app answered last, so "why did my bot not hear about this" has an answer.
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "agent_events"
        verbose_name = "Agent event"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["created_at"], name="agent_event_created"),
            models.Index(fields=["grant", "-created_at"], name="agent_event_grant"),
        ]
