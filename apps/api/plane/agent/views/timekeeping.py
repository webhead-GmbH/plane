# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A person's working days, hours and running timer, and their leave."""

# Python imports
from datetime import timedelta

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.agent.scopes import LEAVE_READ, TIME_READ, WORK_ITEMS_READ
from plane.agent.services import dates
from plane.agent.services import timekeeping as timing
from plane.agent.services.employment import employment_for, today_for, zone_name_for
from plane.agent.views.base import AgentAPIView
from plane.hr.services.leave import standing as leave_standing
from plane.hr.services.ledger import day_outlook
from plane.hr.models import HrContract
from plane.hr.utils.resolve import effective


class _TimeView(AgentAPIView):
    required_scope = TIME_READ

    def setup_person(self, request):
        self.profile = employment_for(request.user)
        self.zone = zone_name_for(request.user, self.profile)
        self.today = today_for(request.user, self.profile)
        scopes = request.auth.scopes
        self.with_leave_detail = LEAVE_READ in scopes
        self.with_work_items = WORK_ITEMS_READ in scopes

    def not_employed(self, **extra):
        return Response({"employed": False, "timezone": self.zone, **extra}, status=status.HTTP_200_OK)


class DayEndpoint(_TimeView):
    """What one day is for this person, and what they have done on it so far."""

    def get(self, request):
        self.setup_person(request)
        day = dates.parse_date(request.query_params.get("date"), "date") or self.today
        if self.profile is None:
            return self.not_employed(date=day.isoformat(), day=None)

        outlook = day_outlook(self.profile, day, day)[0]
        payload = timing.day_payload(outlook, with_leave_detail=self.with_leave_detail)
        summary = timing.summarize(request.user, self.profile, day, day, self.zone, with_work_items=False)
        payload["worked_minutes"] = summary["total_minutes"]
        payload["is_today"] = day == self.today
        payload["timer_running"] = timing.running_timer(request.user, with_work_item=False) is not None
        return Response(
            {"employed": True, "timezone": self.zone, "today": self.today.isoformat(), "day": payload},
            status=status.HTTP_200_OK,
        )


class DaysEndpoint(_TimeView):
    """A span of days: which are working days, which are holidays, which the person is away."""

    def get(self, request):
        self.setup_person(request)
        first, last = dates.parse_span(request.query_params, self.today, default_days=7)
        if self.profile is None:
            return self.not_employed(**{"from": first.isoformat(), "to": last.isoformat(), "days": []})

        days = [
            timing.day_payload(outlook, with_leave_detail=self.with_leave_detail)
            for outlook in day_outlook(self.profile, first, last)
        ]
        return Response(
            {
                "employed": True,
                "timezone": self.zone,
                "today": self.today.isoformat(),
                "from": first.isoformat(),
                "to": last.isoformat(),
                "expected_minutes": sum(item["expected_minutes"] for item in days),
                "working_days": sum(1 for item in days if item["expects_work"]),
                "days": days,
            },
            status=status.HTTP_200_OK,
        )


class TimeSummaryEndpoint(_TimeView):
    """Hours worked between two days, per day and (if allowed) per work item."""

    def get(self, request):
        self.setup_person(request)
        first, last = dates.parse_span(request.query_params, self.today - timedelta(days=6), default_days=7)
        summary = timing.summarize(
            request.user, self.profile, first, last, self.zone, with_work_items=self.with_work_items
        )
        summary["employed"] = self.profile is not None
        summary["timer"] = timing.running_timer(request.user, with_work_item=self.with_work_items)
        return Response(summary, status=status.HTTP_200_OK)


class TimerEndpoint(_TimeView):
    """The timer the person has running, if any. One at a time, across every workspace."""

    def get(self, request):
        self.setup_person(request)
        timer = timing.running_timer(request.user, with_work_item=self.with_work_items)
        return Response({"running": timer is not None, "timer": timer}, status=status.HTTP_200_OK)


class _LeaveView(AgentAPIView):
    required_scope = LEAVE_READ


class LeaveEndpoint(_LeaveView):
    """How much leave the person has left in the current leave year."""

    def get(self, request):
        profile = employment_for(request.user)
        if profile is None:
            return Response({"employed": False, "leave": None}, status=status.HTTP_200_OK)
        today = today_for(request.user, profile)
        contract = effective(list(HrContract.objects.filter(profile_id=profile.id)), today)
        keeps_account = contract is None or contract.records_leave_account
        standing = leave_standing(profile, today) if keeps_account else None
        leave = None
        if standing is not None:
            leave = {
                "leave_year_start": standing["leave_year_start"].isoformat(),
                "leave_year_end": standing["leave_year_end"].isoformat(),
                "granted_minutes": standing["granted_minutes"],
                "taken_minutes": standing["taken_minutes"],
                "remaining_minutes": standing["remaining_minutes"],
                "is_final": standing["is_final"],
            }
        return Response(
            {"employed": True, "keeps_leave_account": keeps_account, "leave": leave}, status=status.HTTP_200_OK
        )


class AbsencesEndpoint(_LeaveView):
    """The person's approved absences in a span, with what kind each is."""

    def get(self, request):
        profile = employment_for(request.user)
        today = today_for(request.user, profile)
        first, last = dates.parse_span(request.query_params, today, default_days=30)
        if profile is None:
            return Response({"employed": False, "absences": []}, status=status.HTTP_200_OK)
        absences = timing.approved_absences(profile, first, last)
        return Response(
            {
                "employed": True,
                "from": first.isoformat(),
                "to": last.isoformat(),
                "absences": [
                    {
                        "start_date": absence.start_date.isoformat(),
                        "end_date": absence.end_date.isoformat(),
                        "type": {
                            "code": absence.absence_type.code,
                            "name": timing.absence_type_name(absence.absence_type),
                        },
                        "granularity": timing.GRANULARITY_NAMES.get(absence.granularity, "full_day"),
                        "start_half": timing.HALF_NAMES.get(absence.start_half),
                        "end_half": timing.HALF_NAMES.get(absence.end_half),
                        "minutes_per_day": absence.minutes_per_day,
                    }
                    for absence in absences
                ],
            },
            status=status.HTTP_200_OK,
        )
