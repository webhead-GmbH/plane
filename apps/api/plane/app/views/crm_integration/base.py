# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.conf import settings

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.db.models import CrmIntegration, Workspace
from plane.app.permissions import allow_permission, ROLE
from plane.app.serializers import CrmIntegrationSerializer
from plane.utils.crm_client import CrmApiClient, CrmApiError
from ..base import BaseAPIView

# Interactive endpoints (test / fetch) run inside the request/response cycle, so
# they use a short timeout to avoid tying up a worker on a slow or hung CRM.
INTERACTIVE_CRM_TIMEOUT = 15


def _is_valid_crm_url(url):
    """Only http(s) URLs may be contacted (defence-in-depth for admin-supplied URLs)."""
    return isinstance(url, str) and url.lower().startswith(("http://", "https://"))


class CrmIntegrationEndpoint(BaseAPIView):
    """Workspace-admin CRUD for the single CRM integration of a workspace."""

    def _get_integration(self, slug):
        return CrmIntegration.objects.filter(workspace__slug=slug).first()

    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug):
        integration = self._get_integration(slug)
        if integration is None:
            # No configuration yet — return an empty body so the UI can render a
            # blank form without treating it as an error.
            return Response({}, status=status.HTTP_200_OK)
        return Response(
            CrmIntegrationSerializer(integration).data, status=status.HTTP_200_OK
        )

    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        # `workspace` is a OneToOne (DB-unique). A previously soft-deleted row still
        # occupies that unique slot, so inspect `all_objects`, not just `objects`.
        existing = CrmIntegration.all_objects.filter(workspace=workspace).first()
        if existing is not None:
            if existing.deleted_at is None:
                return Response(
                    {"error": "A CRM integration already exists for this workspace. Use PATCH to update it."},
                    status=status.HTTP_409_CONFLICT,
                )
            # purge the soft-deleted remnant so a fresh config can be created
            existing.delete(soft=False)

        serializer = CrmIntegrationSerializer(
            data=request.data, context={"workspace": workspace}
        )
        if serializer.is_valid():
            serializer.save(workspace=workspace)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def patch(self, request, slug):
        integration = self._get_integration(slug)
        if integration is None:
            return Response(
                {"error": "CRM integration not configured."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CrmIntegrationSerializer(
            integration,
            data=request.data,
            partial=True,
            context={"workspace": integration.workspace},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug):
        integration = self._get_integration(slug)
        if integration is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        # Hard-delete: this is a per-workspace singleton keyed by a unique OneToOne,
        # so a soft-deleted remnant would block re-configuration. Cascades the logs.
        integration.delete(soft=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CrmIntegrationTestEndpoint(BaseAPIView):
    """Validate connectivity to the CRM without persisting anything.

    Accepts an optional ``crm_api_url`` / ``crm_api_key`` in the body so the
    admin can test credentials before saving them; otherwise the saved
    configuration is used.
    """

    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        integration = CrmIntegration.objects.filter(workspace__slug=slug).first()

        crm_api_url = request.data.get("crm_api_url") or (
            integration.crm_api_url if integration else None
        )
        crm_api_key = request.data.get("crm_api_key") or (
            integration.get_api_key() if integration else None
        )

        if not crm_api_url or not crm_api_key:
            return Response(
                {"error": "CRM URL and API key are required to test the connection."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not _is_valid_crm_url(crm_api_url):
            return Response(
                {"error": "CRM URL must start with http:// or https://."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = CrmApiClient(
            base_url=crm_api_url,
            api_key=crm_api_key,
            timeout=INTERACTIVE_CRM_TIMEOUT,
            verify=settings.CRM_VERIFY_SSL,
        )
        try:
            projects = client.get_projects()
        except CrmApiError as exc:
            return Response(
                {"success": False, "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {"success": True, "projects_count": len(projects)},
            status=status.HTTP_200_OK,
        )


class CrmIntegrationSyncEndpoint(BaseAPIView):
    """Push every existing work item and worklog to the CRM once.

    Day-to-day the sync is event-driven, so this is only needed to seed a CRM
    that was connected after the work already existed. Anything already linked is
    updated instead of duplicated, so it is safe to run more than once.
    """

    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        integration = CrmIntegration.objects.filter(workspace__slug=slug).first()
        if integration is None:
            return Response(
                {"error": "CRM integration not configured."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not integration.is_active:
            return Response(
                {"error": "CRM integration is inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Imported lazily to avoid importing Celery machinery at module load.
        from plane.bgtasks.crm_sync_task import backfill_workspace_to_crm

        backfill_workspace_to_crm.delay(integration_id=str(integration.id))
        return Response(
            {"success": True, "message": "Backfill started."},
            status=status.HTTP_202_ACCEPTED,
        )
