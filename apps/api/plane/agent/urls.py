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
from plane.agent.views.team import TeamEndpoint, TeamWorkItemsEndpoint, TeamWorkloadEndpoint
from plane.agent.views.timekeeping import (
    AbsencesEndpoint,
    DayEndpoint,
    DaysEndpoint,
    LeaveEndpoint,
    TimeSummaryEndpoint,
    TimerEndpoint,
)
from plane.agent.views.work_items import (
    ProjectLabelsEndpoint,
    ProjectListEndpoint,
    ProjectMembersEndpoint,
    ProjectStatesEndpoint,
    WorkItemListEndpoint,
)
from plane.agent.views.writes import (
    AttachmentCreateEndpoint,
    CommentCreateEndpoint,
    TimeEntryCreateEndpoint,
    TimerStartEndpoint,
    TimerStopEndpoint,
    WorkItemCreateEndpoint,
    WorkItemEndpoint,
)

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
    path("v1/workspaces/<str:slug>/work-items/<str:ref>/", WorkItemEndpoint.as_view(), name="agent-work-item"),
    path(
        "v1/workspaces/<str:slug>/projects/<str:project_id>/members/",
        ProjectMembersEndpoint.as_view(),
        name="agent-project-members",
    ),
    path(
        "v1/workspaces/<str:slug>/projects/<str:project_id>/states/",
        ProjectStatesEndpoint.as_view(),
        name="agent-project-states",
    ),
    path(
        "v1/workspaces/<str:slug>/projects/<str:project_id>/labels/",
        ProjectLabelsEndpoint.as_view(),
        name="agent-project-labels",
    ),
    # A manager's team
    path("v1/team/", TeamEndpoint.as_view(), name="agent-team"),
    path("v1/team/workload/", TeamWorkloadEndpoint.as_view(), name="agent-team-workload"),
    path("v1/team/<str:user_id>/work-items/", TeamWorkItemsEndpoint.as_view(), name="agent-team-work-items"),
    # Changing things
    path(
        "v1/workspaces/<str:slug>/projects/<str:project_id>/work-items/",
        WorkItemCreateEndpoint.as_view(),
        name="agent-work-item-create",
    ),
    path(
        "v1/workspaces/<str:slug>/work-items/<str:ref>/comments/",
        CommentCreateEndpoint.as_view(),
        name="agent-comment-create",
    ),
    path(
        "v1/workspaces/<str:slug>/work-items/<str:ref>/attachments/",
        AttachmentCreateEndpoint.as_view(),
        name="agent-attachment-create",
    ),
    path("v1/me/timer/start/", TimerStartEndpoint.as_view(), name="agent-timer-start"),
    path("v1/me/timer/stop/", TimerStopEndpoint.as_view(), name="agent-timer-stop"),
    path("v1/me/time-entries/", TimeEntryCreateEndpoint.as_view(), name="agent-time-entry-create"),
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
