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
from plane.hr.permissions import (
    MANAGER,
    SELF,
    hr_permission,
    readable_profile_or_none,
    visible_profiles,
)
from plane.hr.services.ledger import has_running_timer, period_totals, rebuild_period
from plane.hr.utils.resolve import effective, effective_schedule


def _int_param(request, name, default=None):
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _period_payload(period, include_days=False):
    """A month, with its totals filled in from wherever they currently live."""
    data = HrPeriodSerializer(period).data
    if period.state != HrPeriod.State.LOCKED:
        # Open months carry no stored totals, so they are summed from the days.
        totals = period_totals(period)
        for key, value in totals.items():
            data[key] = value or 0
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
    def get(self, request, slug):
        profile = request.hr_profile
        if profile is None:
            return Response(
                {"profile": None, "is_hr_manager": request.hr_is_manager},
                status=status.HTTP_200_OK,
            )

        today = date.today()
        year = _int_param(request, "year", today.year)
        month = _int_param(request, "month", today.month)

        contracts = list(HrContract.objects.filter(profile_id=profile.id))
        personal = list(HrWorkSchedule.objects.filter(profile_id=profile.id))
        defaults = list(
            HrWorkSchedule.objects.filter(workspace_id=profile.workspace_id, profile__isnull=True)
        )
        contract = effective(contracts, today)
        schedule = effective_schedule(personal, defaults, today)

        period = HrPeriod.objects.filter(profile_id=profile.id, period_start=date(year, month, 1)).first()

        return Response(
            {
                "profile": HrEmploymentProfileSerializer(profile).data,
                "is_hr_manager": request.hr_is_manager,
                "contract": HrContractSerializer(contract).data if contract else None,
                "schedule": HrWorkScheduleSerializer(schedule).data if schedule else None,
                "period": _period_payload(period, include_days=True) if period else None,
                "has_running_timer": has_running_timer(profile, year, month),
            },
            status=status.HTTP_200_OK,
        )


class HrPeriodListEndpoint(BaseAPIView):
    @hr_permission(SELF)
    def get(self, request, slug):
        profile = readable_profile_or_none(
            request, slug, request.query_params.get("profile_id") or None
        )
        if profile is None:
            return Response({"error": "No such person, or not yours to read."}, status=status.HTTP_404_NOT_FOUND)

        periods = HrPeriod.objects.filter(profile_id=profile.id).select_related("profile__member")
        year = _int_param(request, "year")
        if year:
            periods = periods.filter(period_start__year=year)
        return Response(
            [_period_payload(period) for period in periods.order_by("-period_start")],
            status=status.HTTP_200_OK,
        )


class HrPeriodDetailEndpoint(BaseAPIView):
    def _period_for(self, request, slug, pk):
        return (
            HrPeriod.objects.filter(pk=pk, profile__in=visible_profiles(request, slug))
            .select_related("profile__member")
            .first()
        )

    @hr_permission(SELF)
    def get(self, request, slug, pk):
        period = self._period_for(request, slug, pk)
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
    def get(self, request, slug, pk):
        period = HrPeriod.objects.filter(pk=pk, profile__in=visible_profiles(request, slug)).first()
        if period is None:
            return Response({"error": "No such month, or not yours to read."}, status=status.HTTP_404_NOT_FOUND)
        days = HrPeriodDay.objects.filter(period_id=period.id).order_by("work_date")
        return Response(HrPeriodDaySerializer(days, many=True).data, status=status.HTTP_200_OK)


class HrPeriodRecomputeEndpoint(BaseAPIView):
    @hr_permission(SELF)
    def post(self, request, slug, pk):
        period = HrPeriod.objects.filter(pk=pk, profile__in=visible_profiles(request, slug)).first()
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


class HrOverviewEndpoint(BaseAPIView):
    """Everyone's month on one screen.

    Rebuilds each open month before answering, so the figures a manager is about
    to act on are current rather than as of whenever the last scheduled run was.
    """

    @hr_permission(MANAGER)
    def get(self, request, slug):
        today = date.today()
        year = _int_param(request, "year", today.year)
        month = _int_param(request, "month", today.month)
        first = date(year, month, 1)

        rows = []
        for profile in visible_profiles(request, slug).filter(is_active=True).select_related("member"):
            period = HrPeriod.objects.filter(profile_id=profile.id, period_start=first).first()
            if period is None or period.state != HrPeriod.State.LOCKED:
                rebuild_period(profile, year, month, actor=request.user)
                period = HrPeriod.objects.filter(profile_id=profile.id, period_start=first).first()
            if period is None:
                continue

            payload = _period_payload(period)
            payload["member_display_name"] = profile.member.display_name
            payload["needs_review"] = HrPeriodDay.objects.filter(
                period_id=period.id, needs_review=True
            ).exists()
            payload["has_running_timer"] = has_running_timer(profile, year, month)
            rows.append(payload)

        return Response({"year": year, "month": month, "rows": rows}, status=status.HTTP_200_OK)
