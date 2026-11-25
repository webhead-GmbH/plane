# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Everything under /api/instances/agent-apps/: the administrators' screen for connected apps.

It sits under `/api/instances/` on purpose. The session middleware picks the admin app's
own cookie for paths with `instances` in them, so a person who is signed in to Plane as an
administrator in another tab is not, for this screen, the administrator.
"""

from django.urls import path

from plane.agent.views.admin import (
    AgentAppConnectionsEndpoint,
    AgentAppEndpoint,
    AgentAppListEndpoint,
    AgentAppSecretEndpoint,
    AgentAppWebhookEndpoint,
    AgentAppWebhookSecretEndpoint,
    AgentAppWebhookTestEndpoint,
)

urlpatterns = [
    path("", AgentAppListEndpoint.as_view(), name="agent-admin-apps"),
    path("<str:client_id>/", AgentAppEndpoint.as_view(), name="agent-admin-app"),
    path("<str:client_id>/secret/", AgentAppSecretEndpoint.as_view(), name="agent-admin-app-secret"),
    path("<str:client_id>/webhook/", AgentAppWebhookEndpoint.as_view(), name="agent-admin-app-webhook"),
    path(
        "<str:client_id>/webhook/secret/",
        AgentAppWebhookSecretEndpoint.as_view(),
        name="agent-admin-app-webhook-secret",
    ),
    path("<str:client_id>/webhook/test/", AgentAppWebhookTestEndpoint.as_view(), name="agent-admin-app-webhook-test"),
    path("<str:client_id>/connections/", AgentAppConnectionsEndpoint.as_view(), name="agent-admin-app-connections"),
    path(
        "<str:client_id>/connections/<uuid:grant_id>/",
        AgentAppConnectionsEndpoint.as_view(),
        name="agent-admin-app-connection",
    ),
]
