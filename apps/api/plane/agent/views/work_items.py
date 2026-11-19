# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The projects and work items a connected person can see."""

# Python imports
# Django imports
from django.db.models import Exists, OuterRef, Q

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.agent.errors import invalid_request, not_found
from plane.agent.scopes import WORK_ITEMS_READ
from plane.agent.services import dates, work_items
from plane.agent.views.base import AgentAPIView
from plane.agent.views.me import ROLE_NAMES
from plane.app.permissions import ROLE
from plane.db.models import IssueAssignee, Label, ProjectMember, State

STATE_GROUPS = ("backlog", "unstarted", "started", "completed", "cancelled")
PRIORITIES = ("urgent", "high", "medium", "low", "none")
# What a list may be ordered by. Anything else is refused rather than passed to the database.
ORDERINGS = {
    "updated_at": "updated_at",
    "-updated_at": "-updated_at",
    "created_at": "created_at",
    "-created_at": "-created_at",
    "target_date": "target_date",
    "-target_date": "-target_date",
}


def _choices(raw, allowed, name):
    """A comma-separated query value, every part of which must be one of `allowed`."""
    if not raw:
        return []
    values = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise invalid_request(f"{name} must be one of: {', '.join(allowed)}.")
    return values


def _uuid(raw, name):
    return work_items.parse_uuid(raw, name)


class ProjectListEndpoint(AgentAPIView):
    """The projects the person is a member of."""

    required_scope = WORK_ITEMS_READ

    def get(self, request):
        projects = work_items.visible_projects(request.user).select_related("workspace")
        if request.query_params.get("workspace"):
            projects = projects.filter(workspace__slug=request.query_params["workspace"])
        roles = dict(
            ProjectMember.objects.filter(member=request.user, is_active=True).values_list("project_id", "role")
        )
        return Response(
            {
                "results": [
                    {
                        "id": str(project.id),
                        "name": project.name,
                        "identifier": project.identifier,
                        "workspace": project.workspace.slug,
                        "description": work_items.plain_text(project.description, 2000),
                        "role": ROLE_NAMES.get(roles.get(project.id), "guest"),
                    }
                    for project in projects.order_by("workspace__slug", "name")
                ]
            },
            status=status.HTTP_200_OK,
        )


class WorkItemListEndpoint(AgentAPIView):
    """Work items the person can see, narrowed by what the app asks for."""

    required_scope = WORK_ITEMS_READ

    def get(self, request):
        query = request.query_params
        limit, offset = dates.parse_page(query)

        items = work_items.visible_issues(request.user)
        if query.get("workspace"):
            items = items.filter(workspace__slug=query["workspace"])
        if query.get("project"):
            items = items.filter(project_id=_uuid(query["project"], "project"))

        assignee = query.get("assignee")
        if assignee == "me":
            items = items.filter(Exists(IssueAssignee.objects.filter(issue_id=OuterRef("id"), assignee=request.user)))
        elif assignee:
            raise invalid_request("assignee must be 'me'.")

        groups = _choices(query.get("state_group"), STATE_GROUPS, "state_group")
        if groups:
            items = items.filter(state__group__in=groups)
        priorities = _choices(query.get("priority"), PRIORITIES, "priority")
        if priorities:
            items = items.filter(priority__in=priorities)

        due_before, due_after = (
            dates.parse_date(query.get("due_before"), "due_before"),
            dates.parse_date(query.get("due_after"), "due_after"),
        )
        if due_before:
            items = items.filter(target_date__lte=due_before)
        if due_after:
            items = items.filter(target_date__gte=due_after)
        updated_since = dates.parse_datetime(query.get("updated_since"), "updated_since")
        if updated_since:
            items = items.filter(updated_at__gte=updated_since)

        text = (query.get("q") or "").strip()
        if text:
            if len(text) > 200:
                raise invalid_request("q is too long.")
            items = items.filter(Q(name__icontains=text) | Q(description_stripped__icontains=text))

        order = ORDERINGS.get(query.get("order_by", "-updated_at"))
        if order is None:
            raise invalid_request(f"order_by must be one of: {', '.join(ORDERINGS)}.")

        total = items.count()
        page = work_items.with_relations(work_items.with_my_time(items, request.user)).order_by(order, "id")[
            offset : offset + limit
        ]
        results = [work_items.compact(issue) for issue in page]
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": offset + limit if offset + limit < total else None,
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


class _ProjectLookup(AgentAPIView):
    """What an app needs to know about a project before it can create or change work in it."""

    required_scope = WORK_ITEMS_READ

    def project(self, request, slug, project_id):
        project = (
            work_items.visible_projects(request.user)
            .filter(pk=work_items.parse_uuid(project_id, "project_id"), workspace__slug=slug)
            .first()
        )
        if project is None:
            raise not_found("No such project, or you are not a member of it.")
        return project


class ProjectMembersEndpoint(_ProjectLookup):
    """The people in a project, who can be named when assigning work."""

    def get(self, request, slug, project_id):
        project = self.project(request, slug, project_id)
        members = (
            ProjectMember.objects.filter(project=project, is_active=True, member__is_bot=False)
            .select_related("member")
            .order_by("member__display_name")
        )
        return Response(
            {
                "results": [
                    {
                        "id": str(member.member_id),
                        "display_name": member.member.display_name,
                        "role": ROLE_NAMES.get(member.role, "guest"),
                        # Guests can see work but cannot be assigned it.
                        "can_be_assigned": member.role >= ROLE.MEMBER.value,
                    }
                    for member in members
                ]
            },
            status=status.HTTP_200_OK,
        )


class ProjectStatesEndpoint(_ProjectLookup):
    """The states a work item in this project can be in."""

    def get(self, request, slug, project_id):
        project = self.project(request, slug, project_id)
        states = State.objects.filter(project=project).order_by("sequence", "name")
        return Response(
            {
                "results": [
                    {"id": str(state.id), "name": state.name, "group": state.group, "default": state.default}
                    for state in states
                ]
            },
            status=status.HTTP_200_OK,
        )


class ProjectLabelsEndpoint(_ProjectLookup):
    """The labels that can be put on a work item in this project."""

    def get(self, request, slug, project_id):
        project = self.project(request, slug, project_id)
        labels = Label.objects.filter(project=project).order_by("name")
        return Response(
            {"results": [{"id": str(label.id), "name": label.name, "color": label.color} for label in labels]},
            status=status.HTTP_200_OK,
        )
