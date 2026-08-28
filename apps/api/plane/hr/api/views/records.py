# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Absences and hours that are not attached to a work item.

Both belong to a person, so everything here is scoped to what the caller may see,
and both feed months that eventually close — so once a month is closed, the
records that fed it stop accepting changes.
"""

# Django imports
from django.utils import timezone

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.views.base import BaseAPIView
from plane.hr.api.serializers.records import (
    HrAbsenceSerializer,
    HrTeamAbsenceSerializer,
    HrTimeEntrySerializer,
)
from plane.hr.models import HrAbsence, HrTimeEntry
from plane.hr.permissions import (
    MANAGER,
    SELF,
    can_approve,
    hr_permission,
    readable_profile_or_none,
    visible_profiles,
)
from plane.hr.services.absences import resolve_total_minutes

_LOCKED = {
    "error": (
        "The month this belongs to has been closed. Reopen it if the record "
        "genuinely needs to change."
    )
}


def _date_window(request, queryset, start_field, end_field=None):
    """Narrow a list to a date range, ignoring anything unparseable."""
    start = request.query_params.get("from")
    end = request.query_params.get("to")
    if start:
        queryset = queryset.filter(**{f"{end_field or start_field}__gte": start})
    if end:
        queryset = queryset.filter(**{f"{start_field}__lte": end})
    return queryset


class HrAbsenceEndpoint(BaseAPIView):
    """Time away from work."""

    @hr_permission(SELF)
    def get(self, request, pk=None):
        rows = HrAbsence.objects.filter(
            profile__in=visible_profiles(request)
        ).select_related("absence_type", "profile__member")

        if pk is not None:
            row = rows.filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(HrAbsenceSerializer(row).data, status=status.HTTP_200_OK)

        profile_id = request.query_params.get("profile_id")
        if profile_id:
            rows = rows.filter(profile_id=profile_id)
        state = request.query_params.get("state")
        if state and state.isdigit():
            rows = rows.filter(state=int(state))
        rows = _date_window(request, rows, "start_date", "end_date")
        return Response(
            HrAbsenceSerializer(rows.order_by("-start_date"), many=True).data,
            status=status.HTTP_200_OK,
        )

    @hr_permission(SELF)
    def post(self, request):
        profile = readable_profile_or_none(request, request.data.get("profile_id"))
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = HrAbsenceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # A manager recording an agreed absence does not need to request it from
        # themselves; anybody else is asking.
        state = (
            HrAbsence.State.APPROVED if request.hr_is_manager else HrAbsence.State.REQUESTED
        )
        absence = serializer.save(
            workspace_id=profile.workspace_id, profile=profile, state=state
        )
        _settle_minutes(absence)
        if state == HrAbsence.State.APPROVED:
            absence.approved_by = request.user
            absence.approved_at = timezone.now()
            absence.save()
        return Response(HrAbsenceSerializer(absence).data, status=status.HTTP_201_CREATED)

    @hr_permission(SELF)
    def patch(self, request, pk):
        row = HrAbsence.objects.filter(profile__in=visible_profiles(request), pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)
        if not request.hr_is_manager and row.state not in (
            HrAbsence.State.DRAFT,
            HrAbsence.State.REQUESTED,
        ):
            return Response(
                {"error": "This has already been decided. Ask for it to be changed."},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = HrAbsenceSerializer(row, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        absence = serializer.save()
        _settle_minutes(absence)
        return Response(HrAbsenceSerializer(absence).data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def delete(self, request, pk):
        row = HrAbsence.objects.filter(profile__in=visible_profiles(request), pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _settle_minutes(absence):
    """Fix how much time this absence covers, once, against the schedule now."""
    absence.total_minutes = resolve_total_minutes(absence)
    absence.save(update_fields=["total_minutes", "updated_at"])


class HrAbsenceDecisionEndpoint(BaseAPIView):
    """Agreeing to, refusing, or withdrawing a request."""

    def _row(self, request, pk):
        return HrAbsence.objects.filter(
            profile__in=visible_profiles(request), pk=pk
        ).select_related("profile").first()

    @hr_permission(SELF)
    def post(self, request, pk, decision):
        row = self._row(request, pk)
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)

        if decision == "cancel":
            own = getattr(request, "hr_profile", None)
            if not request.hr_is_manager and (own is None or own.pk != row.profile_id):
                return Response(
                    {"error": "You don't have the required permissions."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            row.state = HrAbsence.State.CANCELLED
            row.save()
            return Response(HrAbsenceSerializer(row).data, status=status.HTTP_200_OK)

        if not can_approve(request, row.profile):
            return Response(
                {"error": "Deciding on your own absence is not a decision. Ask someone else."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if row.state != HrAbsence.State.REQUESTED:
            return Response(
                {"error": "Only a request that is still open can be decided."},
                status=status.HTTP_409_CONFLICT,
            )

        if decision == "approve":
            row.state = HrAbsence.State.APPROVED
            row.approved_by = request.user
            row.approved_at = timezone.now()
            row.total_minutes = resolve_total_minutes(row)
        else:
            reason = (request.data.get("reason") or "").strip()
            if not reason:
                return Response(
                    {"error": "Say why it is being refused."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            row.state = HrAbsence.State.REJECTED
            row.rejection_reason = reason
        row.save()
        return Response(HrAbsenceSerializer(row).data, status=status.HTTP_200_OK)


class HrAbsenceCalendarEndpoint(BaseAPIView):
    """Who is away, for everybody in the workspace.

    Carries the dates and the person and nothing else. An absence type can imply a
    medical reason, and colleagues have no business with that — which is why this
    uses its own serializer rather than a trimmed version of the full one.
    """

    @hr_permission(SELF)
    def get(self, request):
        rows = HrAbsence.objects.filter(
                        state=HrAbsence.State.APPROVED,
        ).select_related("profile__member")
        rows = _date_window(request, rows, "start_date", "end_date")
        return Response(
            HrTeamAbsenceSerializer(rows.order_by("start_date"), many=True).data,
            status=status.HTTP_200_OK,
        )


class HrTimeEntryEndpoint(BaseAPIView):
    """Hours with no work item behind them, and hours carried over from before."""

    @hr_permission(SELF)
    def get(self, request, pk=None):
        rows = HrTimeEntry.objects.filter(profile__in=visible_profiles(request))
        if pk is not None:
            row = rows.filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(HrTimeEntrySerializer(row).data, status=status.HTTP_200_OK)

        profile_id = request.query_params.get("profile_id")
        if profile_id:
            rows = rows.filter(profile_id=profile_id)
        rows = _date_window(request, rows, "entry_date")
        return Response(
            HrTimeEntrySerializer(rows.order_by("-entry_date"), many=True).data,
            status=status.HTTP_200_OK,
        )

    @hr_permission(SELF)
    def post(self, request):
        profile = readable_profile_or_none(request, request.data.get("profile_id"))
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = HrTimeEntrySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        # Anything entered here is entered by hand. Imports set their own source
        # and carry a batch, which is how the two are told apart afterwards.
        entry = serializer.save(
            workspace_id=profile.workspace_id,
            profile=profile,
            source=HrTimeEntry.Source.MANUAL,
        )
        return Response(HrTimeEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    @hr_permission(SELF)
    def patch(self, request, pk):
        row = HrTimeEntry.objects.filter(profile__in=visible_profiles(request), pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)
        serializer = HrTimeEntrySerializer(row, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @hr_permission(SELF)
    def delete(self, request, pk):
        row = HrTimeEntry.objects.filter(profile__in=visible_profiles(request), pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
