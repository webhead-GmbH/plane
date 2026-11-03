# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.gdrive.views import (
    DriveAuthorizeEndpoint,
    DriveConnectionEndpoint,
    DriveFileEndpoint,
    DriveFileOpenEndpoint,
    DriveFilePreviewEndpoint,
    DriveFoldersEndpoint,
    DriveIssueEndpoint,
    DriveLinkSuggestedEndpoint,
    DriveOAuthCallbackEndpoint,
    DriveProjectFolderEndpoint,
    DriveProjectsEndpoint,
    DriveUploadDetailEndpoint,
    DriveUploadEndpoint,
)

ISSUE = "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/drive"

urlpatterns = [
    path("gdrive/oauth/callback/", DriveOAuthCallbackEndpoint.as_view(), name="gdrive-oauth-callback"),
    path("workspaces/<str:slug>/drive/connection/", DriveConnectionEndpoint.as_view(), name="gdrive-connection"),
    path(
        "workspaces/<str:slug>/drive/connection/authorize/", DriveAuthorizeEndpoint.as_view(), name="gdrive-authorize"
    ),
    path("workspaces/<str:slug>/drive/folders/", DriveFoldersEndpoint.as_view(), name="gdrive-folders"),
    path("workspaces/<str:slug>/drive/projects/", DriveProjectsEndpoint.as_view(), name="gdrive-projects"),
    path(
        "workspaces/<str:slug>/drive/projects/link-suggested/",
        DriveLinkSuggestedEndpoint.as_view(),
        name="gdrive-projects-link-suggested",
    ),
    path(
        "workspaces/<str:slug>/drive/projects/<uuid:project_id>/folder/",
        DriveProjectFolderEndpoint.as_view(),
        name="gdrive-project-folder",
    ),
    path(
        "workspaces/<str:slug>/drive/files/<uuid:file_id>/preview/",
        DriveFilePreviewEndpoint.as_view(),
        name="gdrive-file-preview",
    ),
    path(
        "workspaces/<str:slug>/drive/files/<uuid:file_id>/open/",
        DriveFileOpenEndpoint.as_view(),
        name="gdrive-file-open",
    ),
    path(f"{ISSUE}/", DriveIssueEndpoint.as_view(), name="gdrive-issue"),
    path(f"{ISSUE}/uploads/", DriveUploadEndpoint.as_view(), name="gdrive-uploads"),
    path(f"{ISSUE}/uploads/<uuid:upload_id>/", DriveUploadDetailEndpoint.as_view(), name="gdrive-upload-detail"),
    path(f"{ISSUE}/files/<uuid:file_id>/", DriveFileEndpoint.as_view(), name="gdrive-file"),
]
