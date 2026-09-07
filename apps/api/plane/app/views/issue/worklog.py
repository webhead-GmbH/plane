# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import IntegrityError
from django.db.models import Sum
from django.utils import timezone

# Third Party imports
from rest_framework.response import Response
from rest_framework import status

# Module imports
from .. import BaseViewSet, BaseAPIView
from plane.app.permissions import allow_permission, ROLE
from plane.app.serializers import IssueWorkLogSerializer
from plane.db.models import IssueWorkLog, Issue, ProjectMember, IssueAssignee


def get_timer_allowed_state_groups(project):
    """Effective state groups on which a timer may start: project override, else workspace default."""
    if project.worklog_timer_state_groups is not None:
        return project.worklog_timer_state_groups
    return project.workspace.worklog_timer_state_groups or ["started"]


class IssueWorkLogViewSet(BaseViewSet):
    """CRUD for completed (non-timer) worklogs and manual log creation."""

    serializer_class = IssueWorkLogSerializer
    model = IssueWorkLog

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("slug"))
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(issue_id=self.kwargs.get("issue_id"))
            .filter(duration__isnull=False)  # only completed worklogs in the main list
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
            )
            .select_related("logged_by", "project", "workspace", "issue")
            .order_by("logged_at")
            .distinct()
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def list(self, request, slug, project_id, issue_id):
        queryset = self.get_queryset()
        serializer = IssueWorkLogSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def create(self, request, slug, project_id, issue_id):
        """
        Manual log entry.
        - ADMIN: may supply any logged_by (project member UUID in payload).
        - MEMBER: always logs for themselves.
        """
        is_admin = ProjectMember.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            member=request.user,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()

        logged_by_id = request.user.id
        if is_admin and request.data.get("logged_by"):
            # Verify the target user is a project member
            target_id = request.data["logged_by"]
            if not ProjectMember.objects.filter(
                workspace__slug=slug,
                project_id=project_id,
                member_id=target_id,
                is_active=True,
            ).exists():
                return Response(
                    {"error": "The specified user is not a member of this project."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            logged_by_id = target_id

        duration = request.data.get("duration")
        if not duration or int(duration) <= 0:
            return Response(
                {"error": "A positive duration (in seconds) is required for manual log entries."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = IssueWorkLogSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # A manual entry names its own day, so it can be written straight into a
        # month that has already been settled — where it would sit in the records
        # without ever reaching the figures, because that month is never rebuilt
        # again. Editing one was refused from the start; adding one was not, which
        # left the harder half of the same hole open.
        entered = serializer.validated_data
        settled = self._settled_month_for_a_new_row(logged_by_id, entered.get("started_at"), entered.get("logged_at"))
        if settled is not None:
            return Response(
                {
                    "error": (
                        "These hours fall in a month that has already been settled. "
                        "Reopen it first if they genuinely belong there."
                    ),
                    "period_start": settled.period_start,
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer.save(
            project_id=project_id,
            issue_id=issue_id,
            logged_by_id=logged_by_id,
            workspace=Issue.objects.get(pk=issue_id).workspace,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _settled_month_for_a_new_row(self, logged_by_id, started_at, logged_at):
        """The settled month a row about to be written would land in, or None.

        Asked of the moments the payload carries rather than of a saved row, since
        there is nothing saved yet. An entry that names neither falls on today,
        and today cannot be in a settled month — a month is refused closure until
        it has finished happening.
        """
        from plane.hr.services.settled import settled_month_for

        moment = started_at or logged_at
        if moment is None:
            return None
        return settled_month_for(logged_by_id, moment)

    def _can_modify_worklog(self, request, slug, project_id, worklog):
        """Admins may modify any worklog; everyone else only their own (by logged_by)."""
        if worklog.logged_by_id == request.user.id:
            return True
        return ProjectMember.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            member=request.user,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()

    def _settled_month(self, worklog, *proposed):
        """The closed month this change would disturb, or None.

        An hour that a settled month counted is part of a figure somebody has
        already read — approved, handed to payroll, or invoiced on. That month is
        never rebuilt again, so changing the hour now cannot correct it: it only
        makes the record and the figure disagree. Moving an hour out of one bills
        it a second time in the month it lands in.

        Asked here rather than in the serializer because it is a fact about the
        person's month, not about the row.
        """
        from plane.hr.services.settled import occurred_at, settled_month_for

        return settled_month_for(worklog.logged_by_id, occurred_at(worklog), *proposed)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def partial_update(self, request, slug, project_id, issue_id, pk):
        worklog = IssueWorkLog.objects.get(workspace__slug=slug, project_id=project_id, issue_id=issue_id, pk=pk)
        if not self._can_modify_worklog(request, slug, project_id, worklog):
            return Response(
                {"error": "You can only edit your own worklogs."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = IssueWorkLogSerializer(worklog, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Both the day it is on and the day it would move to: leaving a settled
        # month double-counts the hours, arriving in one loses them. The second is
        # worked out from the row as the edit would leave it rather than from the
        # payload, because clearing the start moves the day to the logged time
        # without the payload saying anything about it.
        after = serializer.validated_data
        moving_to = after.get("started_at", worklog.started_at) or after.get("logged_at", worklog.logged_at)
        settled = self._settled_month(worklog, moving_to)
        if settled is not None:
            return Response(
                {
                    "error": (
                        "These hours belong to a month that has already been settled. "
                        "Reopen it first if they genuinely need to change."
                    ),
                    "period_start": settled.period_start,
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def destroy(self, request, slug, project_id, issue_id, pk):
        worklog = IssueWorkLog.objects.get(workspace__slug=slug, project_id=project_id, issue_id=issue_id, pk=pk)
        if not self._can_modify_worklog(request, slug, project_id, worklog):
            return Response(
                {"error": "You can only delete your own worklogs."},
                status=status.HTTP_403_FORBIDDEN,
            )
        settled = self._settled_month(worklog)
        if settled is not None:
            return Response(
                {
                    "error": (
                        "These hours belong to a month that has already been settled. "
                        "Reopen it first if they genuinely need to be removed."
                    ),
                    "period_start": settled.period_start,
                },
                status=status.HTTP_409_CONFLICT,
            )
        worklog.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueTimerEndpoint(BaseAPIView):
    """
    GET   — Returns the caller's active timer for this issue (if any), or null.
    POST  — Start a timer. Auto-stops any other active timer for this user.
    PATCH — Stop the active timer; optionally accepts { description }.
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id, issue_id):
        try:
            worklog = IssueWorkLog.objects.select_related("issue", "project").get(
                workspace__slug=slug,
                project_id=project_id,
                issue_id=issue_id,
                logged_by=request.user,
                duration__isnull=True,
            )
            return Response(IssueWorkLogSerializer(worklog).data, status=status.HTTP_200_OK)
        except IssueWorkLog.DoesNotExist:
            return Response(None, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id, issue_id):
        """Start a timer. Only issue assignees can start; auto-stops previous active timer."""
        # Validate that the user is assigned to this issue
        is_assignee = IssueAssignee.objects.filter(
            issue_id=issue_id,
            assignee=request.user,
        ).exists()

        # Admins who are explicitly assigned can also start the timer
        if not is_assignee:
            return Response(
                {"error": "Only assignees of this issue can start the timer."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Enforce the workspace/project state-group policy for starting a timer
        issue = Issue.objects.select_related("workspace", "project", "state").get(pk=issue_id)
        allowed_groups = get_timer_allowed_state_groups(issue.project)
        if not issue.state or issue.state.group not in allowed_groups:
            return Response(
                {"error": "A timer cannot be started on a work item in its current state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Auto-stop any pre-existing active timer for this user (on any issue)
        existing = IssueWorkLog.objects.filter(
            logged_by=request.user,
            duration__isnull=True,
        ).first()

        if existing:
            elapsed = int((timezone.now() - existing.started_at).total_seconds())
            existing.duration = max(elapsed, 1)
            existing.save(update_fields=["duration", "updated_at"])

        # Create the new timer entry
        try:
            worklog = IssueWorkLog.objects.create(
                workspace=issue.workspace,
                project_id=project_id,
                issue_id=issue_id,
                logged_by=request.user,
                started_at=timezone.now(),
                logged_at=timezone.now(),
                duration=None,
                created_by=request.user,
                updated_by=request.user,
            )
        except IntegrityError:
            return Response(
                {"error": "A timer is already running for this issue."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(IssueWorkLogSerializer(worklog).data, status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def patch(self, request, slug, project_id, issue_id):
        """
        Stop a running timer with an optional description.
        By default stops the caller's own timer; an admin may stop another user's timer by
        passing { worklog_id } (used by the worklog overview admin controls).
        """
        worklog_id = request.data.get("worklog_id")
        filters = {
            "workspace__slug": slug,
            "project_id": project_id,
            "issue_id": issue_id,
            "duration__isnull": True,
        }

        if worklog_id:
            is_admin = ProjectMember.objects.filter(
                workspace__slug=slug,
                project_id=project_id,
                member=request.user,
                role=ROLE.ADMIN.value,
                is_active=True,
            ).exists()
            target = IssueWorkLog.objects.filter(**filters, pk=worklog_id).first()
            # only admins may stop someone else's timer; anyone may stop their own
            if target and target.logged_by_id != request.user.id and not is_admin:
                return Response(
                    {"error": "Only admins can stop another user's timer."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            worklog = target
        else:
            worklog = IssueWorkLog.objects.filter(**filters, logged_by=request.user).first()

        if not worklog:
            return Response(
                {"error": "No active timer found for this issue."},
                status=status.HTTP_404_NOT_FOUND,
            )

        elapsed = int((timezone.now() - worklog.started_at).total_seconds())
        worklog.duration = max(elapsed, 1)
        if request.data.get("description") is not None:
            worklog.description = request.data.get("description") or None
        worklog.updated_by = request.user
        worklog.save(update_fields=["duration", "description", "updated_by", "updated_at"])

        return Response(IssueWorkLogSerializer(worklog).data, status=status.HTTP_200_OK)


class IssueActiveTimersEndpoint(BaseAPIView):
    """GET — all running timers for an issue (any user), used for the 'who is working on this' banner."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, issue_id):
        worklogs = (
            IssueWorkLog.objects.filter(
                workspace__slug=slug,
                project_id=project_id,
                issue_id=issue_id,
                duration__isnull=True,
            )
            .select_related("logged_by", "issue", "project")
            .order_by("started_at")
        )
        serializer = IssueWorkLogSerializer(worklogs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserActiveTimerEndpoint(BaseAPIView):
    """
    GET — Returns the caller's single running timer anywhere in the workspace, or null.
    Used by the list/board views to render a Start/Stop timer button per row.
    """

    def get(self, request, slug):
        try:
            worklog = IssueWorkLog.objects.select_related("issue", "issue__project").get(
                workspace__slug=slug,
                logged_by=request.user,
                duration__isnull=True,
            )
        except IssueWorkLog.DoesNotExist:
            return Response(None, status=status.HTTP_200_OK)

        # issue_detail (work item name + identifier) is emitted by the serializer.
        return Response(IssueWorkLogSerializer(worklog).data, status=status.HTTP_200_OK)


class IssueWorkLogSummaryEndpoint(BaseAPIView):
    """
    GET — Returns total tracked seconds and all completed worklogs for an issue.
    Used by the sidebar "Tracked time" property.
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, issue_id):
        worklogs = (
            IssueWorkLog.objects.filter(
                workspace__slug=slug,
                project_id=project_id,
                issue_id=issue_id,
                duration__isnull=False,
            )
            .filter(
                project__project_projectmember__member=request.user,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
            )
            .select_related("logged_by", "issue", "project")
            .distinct()
        )

        total = worklogs.aggregate(total=Sum("duration"))["total"] or 0
        serializer = IssueWorkLogSerializer(worklogs, many=True)
        return Response(
            {"total_duration": total, "worklogs": serializer.data},
            status=status.HTTP_200_OK,
        )
