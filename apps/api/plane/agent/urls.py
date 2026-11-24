# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Everything under /api/agent/.

Two families that must not be mixed up. `v1/` is for connected apps and takes their
bearer tokens and nothing else. The rest is for the web app, takes the person's
browser session and nothing else.
"""

from django.urls import path

from plane.agent.views.consent import (
    ConnectionDetailEndpoint,
    ConnectionListEndpoint,
    ConsentApproveEndpoint,
    ConsentDenyEndpoint,
    ConsentEndpoint,
)
from plane.agent.views.me import MeEndpoint
from plane.agent.views.oauth import AuthorizationRequestEndpoint, RevokeEndpoint, TokenEndpoint
from plane.agent.views.timekeeping import (
    AbsencesEndpoint,
    DayEndpoint,
    DaysEndpoint,
    LeaveEndpoint,
    TimeSummaryEndpoint,
    TimerEndpoint,
)
from plane.agent.views.work_items import ProjectListEndpoint, WorkItemDetailEndpoint, WorkItemListEndpoint

# For connected apps
v1_patterns = [
    path("v1/oauth/requests/", AuthorizationRequestEndpoint.as_view(), name="agent-oauth-requests"),
    path("v1/oauth/token/", TokenEndpoint.as_view(), name="agent-oauth-token"),
    path("v1/oauth/revoke/", RevokeEndpoint.as_view(), name="agent-oauth-revoke"),
    path("v1/me/", MeEndpoint.as_view(), name="agent-me"),
    # Working days, hours, timer and leave
    path("v1/me/day/", DayEndpoint.as_view(), name="agent-day"),
    path("v1/me/days/", DaysEndpoint.as_view(), name="agent-days"),
    path("v1/me/time/", TimeSummaryEndpoint.as_view(), name="agent-time"),
    path("v1/me/timer/", TimerEndpoint.as_view(), name="agent-timer"),
    path("v1/me/leave/", LeaveEndpoint.as_view(), name="agent-leave"),
    path("v1/me/absences/", AbsencesEndpoint.as_view(), name="agent-absences"),
    # Projects and work items
    path("v1/projects/", ProjectListEndpoint.as_view(), name="agent-projects"),
    path("v1/work-items/", WorkItemListEndpoint.as_view(), name="agent-work-items"),
    path("v1/workspaces/<str:slug>/work-items/<str:ref>/", WorkItemDetailEndpoint.as_view(), name="agent-work-item"),
]

# For the web app
session_patterns = [
    path("connect/<str:request_token>/", ConsentEndpoint.as_view(), name="agent-consent"),
    path("connect/<str:request_token>/approve/", ConsentApproveEndpoint.as_view(), name="agent-consent-approve"),
    path("connect/<str:request_token>/deny/", ConsentDenyEndpoint.as_view(), name="agent-consent-deny"),
    path("connections/", ConnectionListEndpoint.as_view(), name="agent-connections"),
    path("connections/<uuid:pk>/", ConnectionDetailEndpoint.as_view(), name="agent-connection-detail"),
]

urlpatterns = v1_patterns + session_patterns
