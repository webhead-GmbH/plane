# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""What changing a project's Project ID would do outside Plane, said before it is saved.

With the CRM mapped by identifier the Project ID is the CRM project number, so changing it moves the
project's CRM tasks to another CRM project, with their timers and hours; and the Drive folders are
named after it. Neither shows on the settings screen, so this is what lets the screen ask first.
"""

# Django imports
from django.conf import settings

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.bgtasks.crm_sync_task import _coerce_crm_project_id
from plane.db.models import CrmIntegration, CrmTaskLink, Project
from plane.gdrive.services import planned_renames
from plane.utils.crm_client import CrmApiClient, CrmApiError
from ..base import BaseAPIView

# Asked while a person waits on a settings screen: a CRM that is slow or down is left out of the answer.
NAME_LOOKUP_TIMEOUT = 5


def _crm_project_name(integration, crm_project_id):
    """What the CRM calls a project, or None when it cannot be read just now.

    A bare number does not say whose project it is, which is how a project ends up under another
    customer's number without anybody noticing.
    """
    api_key = integration.get_api_key()
    if not integration.crm_api_url or not api_key:
        return None
    client = CrmApiClient(
        base_url=integration.crm_api_url, api_key=api_key, timeout=NAME_LOOKUP_TIMEOUT, verify=settings.CRM_VERIFY_SSL
    )
    try:
        for crm_project in client.get_projects():
            if _coerce_crm_project_id(crm_project.get("id")) == crm_project_id:
                return crm_project.get("name") or None
    except CrmApiError:
        return None
    return None


def _crm_impact(project, new_identifier):
    integration = CrmIntegration.objects.filter(
        workspace_id=project.workspace_id,
        is_active=True,
        project_mapping_source=CrmIntegration.ProjectMappingSource.IDENTIFIER,
    ).first()
    if integration is None:
        return None

    current = _coerce_crm_project_id(project.identifier)
    target = _coerce_crm_project_id(new_identifier)
    if current is None and target is None:
        return None  # not a CRM project number before, and not after

    # The tasks the sync will move: the same query it runs, so the number shown is the number that moves.
    tasks = 0
    if target is not None:
        tasks = CrmTaskLink.objects.filter(issue__project_id=project.id).exclude(crm_project_id=target).count()

    return {
        "current": current,
        "target": target,
        "tasks": tasks,
        "target_name": _crm_project_name(integration, target) if target is not None and tasks else None,
    }


class ProjectIdentifierChangeImpactEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="PROJECT")
    def get(self, request, slug, project_id):
        project = Project.objects.filter(pk=project_id, workspace__slug=slug).first()
        if project is None:
            return Response({"error": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

        new_identifier = request.GET.get("identifier", "").strip().upper()
        if not new_identifier:
            return Response({"error": "Identifier is required"}, status=status.HTTP_400_BAD_REQUEST)
        if new_identifier == project.identifier:
            return Response({"crm": None, "drive": None}, status=status.HTTP_200_OK)

        return Response(
            {"crm": _crm_impact(project, new_identifier), "drive": planned_renames(project, new_identifier)},
            status=status.HTTP_200_OK,
        )
