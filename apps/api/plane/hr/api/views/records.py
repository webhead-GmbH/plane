# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Absences and hours that are not attached to a work item.

Both belong to a person, so everything here is scoped to what the caller may see,
and both feed months that eventually close — so once a month is closed, the
records that fed it stop accepting changes.
"""

# Python imports
from datetime import date

# Django imports
from django.utils import timezone

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.views.base import BaseAPIView
from plane.hr.api.serializers.records import (
    HrAbsenceSerializer,
    HrAttendanceDaySerializer,
    HrTeamAbsenceSerializer,
    HrTimeEntrySerializer,
)
from plane.hr.models import HrAbsence, HrAttendanceDay, HrContract, HrPeriod, HrTimeEntry
from plane.hr.permissions import (
    MANAGER,
    SELF,
    can_approve,
    hr_permission,
    readable_profile_or_none,
    visible_profiles,
)
from plane.hr.services.absences import resolve_total_minutes
from plane.hr.services.attendance import net_minutes_for, problem_with
from plane.hr.services.audit import differences, record, snapshot
from plane.hr.services.ledger import rebuild_period
from plane.hr.services.settled import settled_month_across, settled_month_for_profile
from plane.hr.utils.resolve import effective

_LOCKED = {"error": ("The month this belongs to has been closed. Reopen it if the record genuinely needs to change.")}

# A month that has been handed in has not been closed, so nothing in it carries
# the marker that refuses edits — but it has stopped being rebuilt, which means
# anything written into it now would sit in the records without ever reaching
# the figures. Naming the month, and what state it is in, is the difference
# between somebody knowing what to ask for and pressing the same button again.
_SETTLED = {
    HrPeriod.State.SUBMITTED: (
        "%s has been handed in and is waiting to be checked, so its records can no "
        "longer change. Ask for it back if this needs to go in."
    ),
    HrPeriod.State.APPROVED: (
        "%s has been agreed and is waiting to be closed, so its records can no "
        "longer change. Ask for it to be reopened if this needs to go in."
    ),
    HrPeriod.State.LOCKED: (
        "%s has been closed, so its records can no longer change. Ask for it to be reopened if this needs to go in."
    ),
}


# What each state is called when the screen builds the sentence itself.
_SETTLED_NAME = {
    HrPeriod.State.SUBMITTED: "handed_in",
    HrPeriod.State.APPROVED: "agreed",
    HrPeriod.State.LOCKED: "closed",
}


def _refuse_settled(period):
    """The refusal for a month that has stopped being rebuilt, or None for none.

    Asked of the month rather than of the record, because this is the case the
    record cannot answer: a row created after the closing carries no marker at
    all, and would otherwise be accepted into a total nobody will recompute.

    The month goes out as a date rather than as "January 2026": the name of a
    month belongs in the reader's language and their calendar, neither of which
    is knowable here. The English sentence stays as the fallback.
    """
    if period is None:
        return None
    wording = _SETTLED.get(period.state, _SETTLED[HrPeriod.State.LOCKED])
    return {
        "error": wording % period.period_start.strftime("%B %Y"),
        "reason": "month_settled",
        "month": period.period_start.isoformat(),
        "month_state": _SETTLED_NAME.get(period.state, "closed"),
    }


# What is worth having a history of, per kind of record. The fields somebody would
# dispute — how long, which day, what it was — rather than every column.
WATCHED = {
    "absence": (
        "absence_type_id",
        "start_date",
        "end_date",
        "granularity",
        "minutes_per_day",
        "total_minutes",
        "state",
    ),
    "attendance": ("work_date", "started_at_local", "ended_at_local", "break_minutes", "work_location", "net_minutes"),
    "time_entry": ("entry_date", "minutes", "category", "note"),
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
        rows = HrAbsence.objects.filter(profile__in=visible_profiles(request)).select_related(
            "absence_type", "profile__member"
        )

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

        refusal = _refuse_settled(
            settled_month_across(
                profile,
                serializer.validated_data.get("start_date"),
                serializer.validated_data.get("end_date"),
            )
        )
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)

        # A manager recording an agreed absence does not need to request it from
        # themselves; anybody else is asking.
        state = HrAbsence.State.APPROVED if request.hr_is_manager else HrAbsence.State.REQUESTED
        absence = serializer.save(workspace_id=profile.workspace_id, profile=profile, state=state)
        _settle_minutes(absence)
        if state == HrAbsence.State.APPROVED:
            absence.approved_by = request.user
            absence.approved_at = timezone.now()
            absence.save()
        record(
            profile,
            request.user,
            absence,
            "absence_created",
            snapshot(absence, WATCHED["absence"]),
            request=request,
        )
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

        # Both where it is and where it is being moved to. Dragging an absence out
        # of a settled month leaves that month's target standing without it, and
        # dragging one in changes a target nobody will recompute.
        refusal = _refuse_settled(
            settled_month_across(row.profile, row.start_date, row.end_date)
            or settled_month_across(
                row.profile,
                serializer.validated_data.get("start_date", row.start_date),
                serializer.validated_data.get("end_date", row.end_date),
            )
        )
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)

        before = snapshot(row, WATCHED["absence"])
        absence = serializer.save()
        _settle_minutes(absence)
        changed = differences(before, snapshot(absence, WATCHED["absence"]))
        if changed:
            record(
                absence.profile,
                request.user,
                absence,
                "absence_changed",
                changed,
                reason=request.data.get("reason", ""),
                request=request,
            )
        return Response(HrAbsenceSerializer(absence).data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def delete(self, request, pk):
        row = HrAbsence.objects.filter(profile__in=visible_profiles(request), pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)
        refusal = _refuse_settled(settled_month_across(row.profile, row.start_date, row.end_date))
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)
        # Read before it goes: afterwards there is nothing left to describe, and
        # the row cannot even say which one it was — deleting clears its key.
        gone = snapshot(row, WATCHED["absence"])
        profile, gone_id = row.profile, row.id
        row.delete()
        record(profile, request.user, row, "absence_removed", gone, request=request, object_id=gone_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _settle_minutes(absence):
    """Fix how much time this absence covers, once, against the schedule now."""
    absence.total_minutes = resolve_total_minutes(absence)
    absence.save(update_fields=["total_minutes", "updated_at"])


class HrAbsenceDecisionEndpoint(BaseAPIView):
    """Agreeing to, refusing, or withdrawing a request."""

    def _row(self, request, pk):
        return HrAbsence.objects.filter(profile__in=visible_profiles(request), pk=pk).select_related("profile").first()

    @hr_permission(SELF)
    def post(self, request, pk, decision):
        row = self._row(request, pk)
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)
        # Agreeing to an absence is what makes it count against the target, so a
        # decision taken after the month settled changes a figure as surely as
        # editing the dates would.
        refusal = _refuse_settled(settled_month_across(row.profile, row.start_date, row.end_date))
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)

        if decision == "cancel":
            own = getattr(request, "hr_profile", None)
            if not request.hr_is_manager and (own is None or own.pk != row.profile_id):
                return Response(
                    {"error": "You don't have the required permissions."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            row.state = HrAbsence.State.CANCELLED
            row.save()
            record(row.profile, request.user, row, "absence_cancelled", request=request)
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
        record(
            row.profile,
            request.user,
            row,
            "absence_approved" if decision == "approve" else "absence_rejected",
            {"state": {"to": row.state}, "total_minutes": {"to": row.total_minutes}},
            reason=row.rejection_reason,
            request=request,
        )
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


class HrAttendanceDayEndpoint(BaseAPIView):
    """When somebody was at work, and where.

    Separate from the hours they booked to work items: this answers "when was this
    person at work", which the law asks about, while a worklog answers "what did
    those hours go on". Reconciling the two against each other is a later job; the
    record has to exist before anything can be reconciled.

    Kept per person and per day, so leaving and coming back is one row with a
    longer break rather than two rows.
    """

    @hr_permission(SELF)
    def get(self, request, pk=None):
        rows = HrAttendanceDay.objects.filter(profile__in=visible_profiles(request))
        if pk is not None:
            row = rows.filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(HrAttendanceDaySerializer(row).data, status=status.HTTP_200_OK)

        profile_id = request.query_params.get("profile_id")
        if profile_id:
            rows = rows.filter(profile_id=profile_id)
        rows = _date_window(request, rows, "work_date")
        return Response(
            HrAttendanceDaySerializer(rows.order_by("-work_date"), many=True).data,
            status=status.HTTP_200_OK,
        )

    @hr_permission(SELF)
    def post(self, request):
        profile = readable_profile_or_none(request, request.data.get("profile_id"))
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        work_date = serializers_date(request.data.get("work_date"))
        if work_date is None:
            return Response({"work_date": ["Give the day this belongs to."]}, status=status.HTTP_400_BAD_REQUEST)

        refusal = _attendance_not_kept(profile, work_date) or _refuse_settled(
            settled_month_for_profile(profile, work_date)
        )
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)

        serializer = HrAttendanceDaySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        values = dict(serializer.validated_data)
        # The zone the times were given in, snapshotted, so moving somebody
        # elsewhere later does not silently rewrite what their old days meant.
        values.setdefault("local_timezone", profile.timezone)

        day = HrAttendanceDay(workspace_id=profile.workspace_id, profile=profile, **values)
        problem = _reject(day)
        if problem:
            return Response(problem, status=status.HTTP_400_BAD_REQUEST)

        day.net_minutes = net_minutes_for(day)
        day.save()
        _rebuild_month_for(day)
        record(profile, request.user, day, "attendance_recorded", snapshot(day, WATCHED["attendance"]), request=request)
        return Response(HrAttendanceDaySerializer(day).data, status=status.HTTP_201_CREATED)

    @hr_permission(SELF)
    def patch(self, request, pk):
        row = HrAttendanceDay.objects.filter(profile__in=visible_profiles(request), pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)

        serializer = HrAttendanceDaySerializer(row, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        refusal = _refuse_settled(
            settled_month_for_profile(
                row.profile, row.work_date, serializer.validated_data.get("work_date", row.work_date)
            )
        )
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)

        before = snapshot(row, WATCHED["attendance"])
        for field, value in serializer.validated_data.items():
            setattr(row, field, value)

        problem = _reject(row)
        if problem:
            return Response(problem, status=status.HTTP_400_BAD_REQUEST)

        # Anything altered after the fact says so, so a corrected day is never
        # mistaken for what was first written down.
        row.recording_method = HrAttendanceDay.RecordingMethod.CORRECTED
        row.net_minutes = net_minutes_for(row)
        row.save()
        _rebuild_month_for(row)
        changed = differences(before, snapshot(row, WATCHED["attendance"]))
        if changed:
            record(
                row.profile,
                request.user,
                row,
                "attendance_corrected",
                changed,
                reason=request.data.get("note", ""),
                request=request,
            )
        return Response(HrAttendanceDaySerializer(row).data, status=status.HTTP_200_OK)

    @hr_permission(SELF)
    def delete(self, request, pk):
        row = HrAttendanceDay.objects.filter(profile__in=visible_profiles(request), pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)
        refusal = _refuse_settled(settled_month_for_profile(row.profile, row.work_date))
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)
        profile, work_date, gone_id = row.profile, row.work_date, row.id
        gone = snapshot(row, WATCHED["attendance"])
        row.delete()
        rebuild_period(profile, work_date.year, work_date.month)
        record(profile, request.user, row, "attendance_removed", gone, request=request, object_id=gone_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _attendance_not_kept(profile, work_date):
    """Whether this person's contract says attendance is recorded at all.

    It is off by default and turning it on is a deliberate act. Accepting days for
    somebody it was never turned on for would create exactly the record the switch
    exists to withhold.

    Read against the day being recorded rather than today, because the terms in
    force then are the ones that decide whether the day should have been kept.
    """
    contracts = list(HrContract.objects.filter(profile_id=profile.id))
    contract = effective(contracts, work_date)
    if contract is None or not contract.records_attendance:
        return {"error": "Attendance is not recorded for this person."}
    return None


def serializers_date(raw):
    """A date from the payload, or None where it is missing or not one."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def _reject(day):
    problem = problem_with(day)
    return {"error": problem} if problem else None


def _rebuild_month_for(day):
    """The month's figures follow the attendance, so they are rebuilt with it."""
    rebuild_period(day.profile, day.work_date.year, day.work_date.month)


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
        refusal = _refuse_settled(settled_month_for_profile(profile, serializer.validated_data.get("entry_date")))
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)
        # Anything entered here is entered by hand. Imports set their own source
        # and carry a batch, which is how the two are told apart afterwards.
        entry = serializer.save(
            workspace_id=profile.workspace_id,
            profile=profile,
            source=HrTimeEntry.Source.MANUAL,
        )
        # Named as entered on somebody's behalf where that is what happened, since
        # from the row alone the two are indistinguishable afterwards.
        own = getattr(request, "hr_profile", None)
        by_hand = "hours_entered" if own is not None and own.pk == profile.pk else "hours_entered_for_them"
        record(profile, request.user, entry, by_hand, snapshot(entry, WATCHED["time_entry"]), request=request)
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
        refusal = _refuse_settled(
            settled_month_for_profile(
                row.profile, row.entry_date, serializer.validated_data.get("entry_date", row.entry_date)
            )
        )
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)
        before = snapshot(row, WATCHED["time_entry"])
        entry = serializer.save()
        changed = differences(before, snapshot(entry, WATCHED["time_entry"]))
        if changed:
            record(
                entry.profile,
                request.user,
                entry,
                "hours_changed",
                changed,
                reason=request.data.get("note", ""),
                request=request,
            )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @hr_permission(SELF)
    def delete(self, request, pk):
        row = HrTimeEntry.objects.filter(profile__in=visible_profiles(request), pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.locked_period_id:
            return Response(_LOCKED, status=status.HTTP_409_CONFLICT)
        refusal = _refuse_settled(settled_month_for_profile(row.profile, row.entry_date))
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)
        # The most damaging change available here, and the one the row itself can
        # no longer testify to afterwards — not even to which row it was.
        gone = snapshot(row, WATCHED["time_entry"])
        profile, gone_id = row.profile, row.id
        row.delete()
        record(profile, request.user, row, "hours_removed", gone, request=request, object_id=gone_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
