# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A manager's view of the people they manage: who they are, how much room they have, what is on their plate.

The scope is not the whole of the permission. Every call checks, again, that the person
behind the connection is a manager *now* (see `services.team`), so a connection approved
by somebody who has since stopped being one shows them nothing.
"""

# Django imports
from django.db.models import Exists, OuterRef

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.agent import conf
from plane.agent.errors import insufficient_scope, invalid_request
from plane.agent.scopes import TEAM_READ, WORK_ITEMS_READ
from plane.agent.services import dates, work_items
from plane.agent.services import team as team_service
from plane.agent.services.employment import employment_for, today_for
from plane.agent.views.base import AgentAPIView
from plane.agent.views.work_items import narrow, page_of
from plane.db.models import IssueAssignee

# How many people one call may name with `user`.
MAX_NAMED_PEOPLE = conf.TEAM_MAX_PAGE_SIZE


class _TeamView(AgentAPIView):
    required_scope = TEAM_READ
    # Scopes a view needs besides `team:read`.
    also_requires = ()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Every scope first, so a connection that lacks one is told so rather than that it is not a manager, and
        # only then whether the person is one, before anything is read.
        for scope in self.also_requires:
            if scope not in request.auth.scopes:
                raise insufficient_scope(scope)
        team_service.require_manager(request)


class TeamEndpoint(_TeamView):
    """The people on the team, with the Plane user id that identifies each."""

    def get(self, request):
        limit, offset = dates.parse_page(request.query_params)
        people = team_service.active_people()
        total = people.count()
        page = list(people[offset : offset + limit])
        self.audit_subjects(profile.member_id for profile in page)
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": offset + limit if offset + limit < total else None,
                "results": [
                    {**team_service.person_payload(profile), "timezone": team_service.zone_of(profile)}
                    for profile in page
                ],
            },
            status=status.HTTP_200_OK,
        )


class TeamWorkloadEndpoint(_TeamView):
    """How much room each person has in a span, and how much open work they have."""

    def get(self, request):
        query = request.query_params
        limit, offset = dates.parse_page(query, default=conf.TEAM_DEFAULT_PAGE_SIZE, maximum=conf.TEAM_MAX_PAGE_SIZE)
        # The span starts today, in the manager's own zone: it is a question about the coming days, asked by them.
        today = today_for(request.user, employment_for(request.user))
        first, last = dates.parse_span(query, today, default_days=7, max_days=conf.TEAM_MAX_RANGE_DAYS)

        people = team_service.active_people()
        named = _named(query.get("user"))
        if named:
            people = people.filter(member_id__in=named)
        total = people.count()
        profiles = list(people[offset : offset + limit])
        self.audit_subjects(profile.member_id for profile in profiles)

        worked = team_service.worked_minutes(profiles, first, last)
        open_work = team_service.open_work(request.user, profiles, first, last)
        running = team_service.timers_running(profiles)
        with_days = query.get("include") == "days"

        results = []
        for profile in profiles:
            results.append(
                {
                    **team_service.person_payload(profile),
                    "timezone": team_service.zone_of(profile),
                    "capacity": team_service.capacity(profile, first, last, with_days=with_days),
                    "worked": worked[profile.member_id],
                    "timer_running": profile.member_id in running,
                    "open_work": open_work[profile.member_id],
                }
            )
        return Response(
            {
                "from": first.isoformat(),
                "to": last.isoformat(),
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": offset + limit if offset + limit < total else None,
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


def _named(raw):
    """The people a call was narrowed to: a comma-separated list of user ids."""
    if not raw:
        return []
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) > MAX_NAMED_PEOPLE:
        raise invalid_request(f"user may name at most {MAX_NAMED_PEOPLE} people.")
    return [work_items.parse_uuid(part, "user") for part in parts]


class TeamWorkItemsEndpoint(_TeamView):
    """One person's work items, among those the manager can see themselves."""

    # Names and descriptions are `work_items:read`, whoever's they are.
    also_requires = (WORK_ITEMS_READ,)

    def get(self, request, user_id):
        profile = team_service.person_for(user_id)
        self.audit_subjects([profile.member_id])
        items = work_items.visible_issues(request.user).filter(
            Exists(
                IssueAssignee.objects.filter(
                    issue_id=OuterRef("id"),
                    assignee_id=profile.member_id,
                    # Somebody who has left the project is not on its work any more (the counts say the same).
                    assignee__member_project__is_active=True,
                    assignee__member_project__project_id=OuterRef("project_id"),
                )
            )
        )
        # The hours shown on each item are the person's own, not the manager's.
        body = page_of(request.query_params, narrow(request.query_params, items), profile.member)
        for item in body["results"]:
            item["person_logged_minutes"] = item.pop("my_logged_minutes")
        body["person"] = team_service.person_payload(profile)
        return Response(body, status=status.HTTP_200_OK)
