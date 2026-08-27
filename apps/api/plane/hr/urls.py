# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.hr.api.views import (
    HrMeEndpoint,
    HrOverviewEndpoint,
    HrPeriodDaysEndpoint,
    HrPeriodDetailEndpoint,
    HrPeriodListEndpoint,
    HrPeriodRecomputeEndpoint,
)

urlpatterns = [
    path("workspaces/<str:slug>/me/", HrMeEndpoint.as_view(), name="hr-me"),
    path("workspaces/<str:slug>/overview/", HrOverviewEndpoint.as_view(), name="hr-overview"),
    path("workspaces/<str:slug>/periods/", HrPeriodListEndpoint.as_view(), name="hr-periods"),
    path(
        "workspaces/<str:slug>/periods/<uuid:pk>/",
        HrPeriodDetailEndpoint.as_view(),
        name="hr-period-detail",
    ),
    path(
        "workspaces/<str:slug>/periods/<uuid:pk>/days/",
        HrPeriodDaysEndpoint.as_view(),
        name="hr-period-days",
    ),
    path(
        "workspaces/<str:slug>/periods/<uuid:pk>/recompute/",
        HrPeriodRecomputeEndpoint.as_view(),
        name="hr-period-recompute",
    ),
]
