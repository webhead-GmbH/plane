# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views import (
    CrmIntegrationEndpoint,
    CrmIntegrationTestEndpoint,
    CrmIntegrationSyncEndpoint,
    CrmEventsWebhookEndpoint,
    CrmTimerWebhookEndpoint,
    ProjectIdentifierChangeImpactEndpoint,
)


urlpatterns = [
    path(
        "workspaces/<str:slug>/crm-integration/",
        CrmIntegrationEndpoint.as_view(),
        name="crm-integration",
    ),
    path(
        "workspaces/<str:slug>/crm-integration/test/",
        CrmIntegrationTestEndpoint.as_view(),
        name="crm-integration-test",
    ),
    # Kept at .../sync/ so existing clients keep working; it now backfills.
    path(
        "workspaces/<str:slug>/crm-integration/sync/",
        CrmIntegrationSyncEndpoint.as_view(),
        name="crm-integration-backfill",
    ),
    # Called by the CRM, not by a Plane user: authenticated by the body's signature.
    path(
        "workspaces/<str:slug>/crm-integration/timer-webhook/",
        CrmTimerWebhookEndpoint.as_view(),
        name="crm-integration-timer-webhook",
    ),
    # What changing a project's Project ID would do in the CRM and in Drive; the settings screen asks first.
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/identifier-change/",
        ProjectIdentifierChangeImpactEndpoint.as_view(),
        name="project-identifier-change-impact",
    ),
    # Also called by the CRM: the projects and ticket tasks made there.
    path(
        "workspaces/<str:slug>/crm-integration/events/",
        CrmEventsWebhookEndpoint.as_view(),
        name="crm-integration-events-webhook",
    ),
]
