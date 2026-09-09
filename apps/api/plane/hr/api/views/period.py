# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Reading months, and asking for one to be worked out again.

While a month is open its totals are summed from its days rather than kept on the
month itself, so there is only ever one place a figure comes from. They are frozen
onto the month when it closes, and from then on that is what is read.
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
    HrContractSerializer,
    HrEmploymentProfileSerializer,
    HrPeriodDaySerializer,
    HrPeriodSerializer,
    HrWorkScheduleSerializer,
)
from plane.hr.models import HrContract, HrPeriod, HrPeriodDay, HrWorkSchedule
from plane.hr.services.refusal import Refused
from plane.hr.permissions import (
    MANAGER,
    SELF,
    can_approve,
    hr_permission,
    readable_profile_or_none,
    visible_profiles,
)
from plane.hr.services.attendance import telework_days_in_year
from plane.hr.services.leave import standing as leave_standing
from plane.hr.services.closing import TransitionRefused, approve, lock, reopen, submit
from plane.hr.services.ledger import (
    counted_through_for,
    has_running_timer,
    period_totals,
    period_totals_to_date,
    rebuild_period,
    settle_day,
)
from plane.hr.services.worklog_detail import detail_for
from plane.hr.utils.calendar import hr_local_date
from plane.hr.utils.resolve import effective, effective_schedule

# Bounds a date object can actually hold, so a typo in a query string cannot
# reach date() and surface as a server error.
MIN_YEAR = 1970
MAX_YEAR = 2200


def _int_param(request, name, default=None, low=None, high=None):
    """A query parameter as an integer, clamped to something a date can hold.

    Range matters as much as type here: 13 is a perfectly good integer and a
    perfectly bad month, and it would reach ``date()`` and come back as a 500 on
    a request whose only fault was a typo.
    """
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if low is not None and value < low:
        return default
    if high is not None and value > high:
        return default
    return value


def _requested_month(request, profile=None):
    """The month being asked about, defaulting to the one that is current here.

    Taken in the working timezone rather than from the server clock, or for the
    first hour of every month the page would open on the previous one.
    """
    zone = None
    if profile is not None:
        zone = profile.timezone or getattr(profile.workspace, "timezone", "") or None
    today = hr_local_date(timezone.now(), zone)
    year = _int_param(request, "year", today.year, low=MIN_YEAR, high=MAX_YEAR)
    month = _int_param(request, "month", today.month, low=1, high=12)
    return year, month


def _period_payload(period, include_days=False):
    """A month, with its totals filled in from wherever they currently live."""
    data = HrPeriodSerializer(period).data
    if period.state != HrPeriod.State.LOCKED:
        # Open months carry no stored totals, so they are summed from the days.
        totals = period_totals(period)
        for key, value in totals.items():
            data[key] = value or 0

        # A month still running is two figures, not one: what the contract owes
        # for the whole of it, and how the person stands so far. Reporting only
        # the first charges every day that has not arrived as a shortfall, which
        # on the first of the month is the entire month. Sent as a separate block
        # so the whole-month figures keep their meaning and nothing downstream has
        # to know which of the two it is being handed.
        through = counted_through_for(period)
        if through is None or through < period.period_end:
            data["to_date"] = {
                "counted_through": through.isoformat() if through else None,
                **period_totals_to_date(period, through),
            }
    if include_days:
        days = HrPeriodDay.objects.filter(period_id=period.id).order_by("work_date")
        data["days"] = HrPeriodDaySerializer(days, many=True).data
    return data


class HrMeEndpoint(BaseAPIView):
    """Everything the person's own view needs, in one request.

    Gathered together deliberately: the alternative is four round trips before a
    page can render anything, on the screen people open most often.
    """

    @hr_permission(SELF)
    def get(self, request):
        profile = request.hr_profile
        if profile is None:
            return Response(
                {"profile": None, "is_hr_manager": request.hr_is_manager},
                status=status.HTTP_200_OK,
            )

        year, month = _requested_month(request, profile)
        today = hr_local_date(timezone.now(), profile.timezone or getattr(profile.workspace, "timezone", "") or None)

        contracts = list(HrContract.objects.filter(profile_id=profile.id))
        personal = list(HrWorkSchedule.objects.filter(profile_id=profile.id))
        defaults = list(HrWorkSchedule.objects.filter(profile__isnull=True))
        contract = effective(contracts, today)
        schedule = effective_schedule(personal, defaults, today)

        first = date(year, month, 1)
        period = HrPeriod.objects.filter(profile_id=profile.id, period_start=first).first()
        # Bring the month up to date on the way in, the same as the overview does.
        # Without it somebody opening their own hours for the first time is told
        # nothing has been worked out yet and has nothing to press — and after
        # that, the figures would only be as fresh as the last scheduled run.
        # Rebuilding refuses to touch a month that has been handed in, approved or
        # closed, so nothing already agreed can move underneath anybody.
        if period is None or period.state in (HrPeriod.State.OPEN, HrPeriod.State.REOPENED):
            rebuild_period(profile, year, month, actor=request.user)
            period = HrPeriod.objects.filter(profile_id=profile.id, period_start=first).first()

        return Response(
            {
                "profile": HrEmploymentProfileSerializer(profile).data,
                "is_hr_manager": request.hr_is_manager,
                "contract": HrContractSerializer(contract).data if contract else None,
                "schedule": HrWorkScheduleSerializer(schedule).data if schedule else None,
                "period": _period_payload(period, include_days=True) if period else None,
                "has_running_timer": has_running_timer(profile, year, month),
                # Null rather than zero where attendance is not kept for this
                # person: there is no count, and zero would read as one.
                "telework_days_this_year": (
                    telework_days_in_year(profile, year) if contract and contract.records_attendance else None
                ),
                # Null where the switch says no leave account is kept for this
                # person, and null again where one is kept but nobody has said yet
                # what the year's entitlement is.
                "leave": (
                    leave_standing(profile, today) if contract is None or contract.records_leave_account else None
                ),
            },
            status=status.HTTP_200_OK,
        )


class HrPeriodListEndpoint(BaseAPIView):
    @hr_permission(SELF)
    def get(self, request):
        profile = readable_profile_or_none(request, request.query_params.get("profile_id") or None)
        if profile is None:
            return Response({"error": "No such person, or not yours to read."}, status=status.HTTP_404_NOT_FOUND)

        periods = HrPeriod.objects.filter(profile_id=profile.id).select_related("profile__member")
        year = _int_param(request, "year", low=MIN_YEAR, high=MAX_YEAR)
        if year:
            periods = periods.filter(period_start__year=year)
        return Response(
            [_period_payload(period) for period in periods.order_by("-period_start")],
            status=status.HTTP_200_OK,
        )


class HrPeriodDetailEndpoint(BaseAPIView):
    def _period_for(self, request, pk):
        return (
            HrPeriod.objects.filter(pk=pk, profile__in=visible_profiles(request))
            .select_related("profile__member")
            .first()
        )

    @hr_permission(SELF)
    def get(self, request, pk):
        period = self._period_for(request, pk)
        if period is None:
            return Response({"error": "No such month, or not yours to read."}, status=status.HTTP_404_NOT_FOUND)
        payload = _period_payload(period)
        payload["has_running_timer"] = has_running_timer(
            period.profile, period.period_start.year, period.period_start.month
        )
        return Response(payload, status=status.HTTP_200_OK)


class HrPeriodDaysEndpoint(BaseAPIView):
    """The day-by-day breakdown — the same read whether the month is open or closed."""

    @hr_permission(SELF)
    def get(self, request, pk):
        period = HrPeriod.objects.filter(pk=pk, profile__in=visible_profiles(request)).first()
        if period is None:
            return Response({"error": "No such month, or not yours to read."}, status=status.HTTP_404_NOT_FOUND)
        days = HrPeriodDay.objects.filter(period_id=period.id).order_by("work_date")
        return Response(HrPeriodDaySerializer(days, many=True).data, status=status.HTTP_200_OK)


class HrWorklogDetailEndpoint(BaseAPIView):
    """Which work items a month's hours went on, grouped as asked.

    The month has only ever shown a figure per day. This is the answer to the
    question that figure invites — and it is a read: nothing here rebuilds, so
    looking at a month cannot change what it says.

    Scoped to one person on purpose. Unscoped, a manager would get the whole
    company's work-item names and notes in one response, which is a great deal
    more than the number it explains.
    """

    @hr_permission(SELF)
    def get(self, request):
        profile = readable_profile_or_none(request, request.query_params.get("profile_id") or None)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        year, month = _requested_month(request, profile)
        grouping = request.query_params.get("group_by") or "day"
        return Response(detail_for(profile, year, month, grouping), status=status.HTTP_200_OK)


class HrPeriodRecomputeEndpoint(BaseAPIView):
    @hr_permission(SELF)
    def post(self, request, pk):
        period = HrPeriod.objects.filter(pk=pk, profile__in=visible_profiles(request)).first()
        if period is None:
            return Response({"error": "No such month, or not yours to read."}, status=status.HTTP_404_NOT_FOUND)

        rebuilt = rebuild_period(
            period.profile, period.period_start.year, period.period_start.month, actor=request.user
        )
        if rebuilt is None:
            return Response(
                {"error": "This month is closed. Reopen it if it genuinely needs to change."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_period_payload(rebuilt, include_days=True), status=status.HTTP_200_OK)


class HrPeriodDaySettleEndpoint(BaseAPIView):
    """Record that a flagged day has been looked at.

    A month refuses to close while any day is flagged, so this is how the question
    "hours that were counted are no longer there — what happened?" gets an answer
    on the record rather than being cleared away silently.
    """

    @hr_permission(MANAGER)
    def post(self, request, pk, day_id):
        day = HrPeriodDay.objects.filter(pk=day_id, period_id=pk, profile__in=visible_profiles(request)).first()
        if day is None:
            return Response({"error": "No such day."}, status=status.HTTP_404_NOT_FOUND)
        try:
            settle_day(day, request.user, request.data.get("note", ""))
        except Refused as refused:
            return Response({"error": refused.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HrPeriodDaySerializer(day).data, status=status.HTTP_200_OK)


class _TransitionEndpoint(BaseAPIView):
    """Shared plumbing for the four steps of closing a month."""

    def _period_or_none(self, request, pk):
        return (
            HrPeriod.objects.filter(pk=pk, profile__in=visible_profiles(request))
            .select_related("profile__member", "profile__workspace")
            .first()
        )

    def _run(self, request, period, action, **kwargs):
        try:
            updated = action(period, request.user, **kwargs)
        except TransitionRefused as refused:
            return Response(
                {"error": refused.message},
                status=status.HTTP_409_CONFLICT if refused.conflict else status.HTTP_400_BAD_REQUEST,
            )
        return Response(_period_payload(updated), status=status.HTTP_200_OK)


class HrPeriodSubmitEndpoint(_TransitionEndpoint):
    @hr_permission(SELF)
    def post(self, request, pk):
        period = self._period_or_none(request, pk)
        if period is None:
            return Response({"error": "No such month, or not yours to read."}, status=status.HTTP_404_NOT_FOUND)
        return self._run(request, period, submit)


class HrPeriodApproveEndpoint(_TransitionEndpoint):
    @hr_permission(MANAGER)
    def post(self, request, pk):
        period = self._period_or_none(request, pk)
        if period is None:
            return Response({"error": "No such month."}, status=status.HTTP_404_NOT_FOUND)
        if not can_approve(request, period.profile):
            return Response(
                {"error": "Approving your own month is not a decision. Ask someone else."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return self._run(request, period, approve)


class HrPeriodLockEndpoint(_TransitionEndpoint):
    @hr_permission(MANAGER)
    def post(self, request, pk):
        period = self._period_or_none(request, pk)
        if period is None:
            return Response({"error": "No such month."}, status=status.HTTP_404_NOT_FOUND)
        return self._run(request, period, lock)


class HrPeriodReopenEndpoint(_TransitionEndpoint):
    @hr_permission(MANAGER)
    def post(self, request, pk):
        period = self._period_or_none(request, pk)
        if period is None:
            return Response({"error": "No such month."}, status=status.HTTP_404_NOT_FOUND)
        return self._run(request, period, reopen, reason=request.data.get("reason", ""))


class HrOverviewEndpoint(BaseAPIView):
    """Everyone's month on one screen.

    Rebuilds each open month before answering, so the figures a manager is about
    to act on are current rather than as of whenever the last scheduled run was.
    """

    @hr_permission(MANAGER)
    def get(self, request):
        year, month = _requested_month(request, getattr(request, "hr_profile", None))
        first = date(year, month, 1)

        rows = []
        for profile in visible_profiles(request).filter(is_active=True).select_related("member"):
            period = HrPeriod.objects.filter(profile_id=profile.id, period_start=first).first()
            if period is None or period.state != HrPeriod.State.LOCKED:
                rebuild_period(profile, year, month, actor=request.user)
                period = HrPeriod.objects.filter(profile_id=profile.id, period_start=first).first()
            if period is None:
                continue

            payload = _period_payload(period)
            payload["member_display_name"] = profile.member.display_name
            payload["needs_review"] = HrPeriodDay.objects.filter(period_id=period.id, needs_review=True).exists()
            payload["has_running_timer"] = has_running_timer(profile, year, month)
            rows.append(payload)

        return Response({"year": year, "month": month, "rows": rows}, status=status.HTTP_200_OK)
