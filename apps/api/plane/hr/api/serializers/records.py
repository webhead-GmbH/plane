# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""How HR records are presented over the API.

Two things run through all of these. Scope fields — the workspace, and the person
a record belongs to — are always read-only and supplied by the view, so a payload
can never move a record to somebody else. And durations go out as minutes exactly
as they are stored, with formatting left to whatever is displaying them; a
serializer that helpfully converted to hours would be the second place the
conversion lives, and the two would eventually disagree.
"""

# Third-party imports
from rest_framework import serializers

# Module imports
from plane.hr.models import (
    HrAbsence,
    HrAbsenceType,
    HrAttendanceDay,
    HrContract,
    HrEmploymentProfile,
    HrHoliday,
    HrHolidayCalendar,
    HrLeaveEntitlement,
    HrPeriod,
    HrPeriodDay,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.hr.api.serializers.base import HrBaseSerializer


class HrEmploymentProfileSerializer(HrBaseSerializer):
    member_display_name = serializers.CharField(source="member.display_name", read_only=True)
    member_email = serializers.EmailField(source="member.email", read_only=True)
    member_avatar_url = serializers.CharField(source="member.avatar_url", read_only=True)

    class Meta:
        model = HrEmploymentProfile
        fields = [
            "id",
            "member",
            "member_display_name",
            "member_email",
            "member_avatar_url",
            "timezone",
            "holiday_calendar",
            "hire_date",
            "exit_date",
            "is_hr_manager",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["workspace", "created_at", "updated_at"]


class HrContractSerializer(HrBaseSerializer):
    class Meta:
        model = HrContract
        fields = [
            "id",
            "profile",
            "valid_from",
            "valid_to",
            "arrangement",
            "legal_form",
            "records_target_hours",
            "records_attendance",
            "records_leave_account",
            "weekly_minutes",
            "agreed_scope_minutes",
            "shortfall_handling",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["workspace", "profile", "created_at", "updated_at"]

    def validate(self, data):
        valid_from = data.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_to = data.get("valid_to", getattr(self.instance, "valid_to", None))
        if valid_to and valid_from and valid_to < valid_from:
            raise serializers.ValidationError({"valid_to": "The end cannot fall before the start."})

        profile = self.context.get("profile") or getattr(self.instance, "profile", None)
        if profile is not None and valid_from is not None:
            overlapping = HrContract.objects.filter(profile=profile).exclude(
                pk=getattr(self.instance, "pk", None)
            )
            for other in overlapping:
                if other.valid_to is not None and other.valid_to < valid_from:
                    continue
                if valid_to is not None and valid_to < other.valid_from:
                    continue
                raise serializers.ValidationError(
                    {
                        "valid_from": (
                            "This overlaps a contract already recorded for this person. "
                            "End the previous one first, so each day has exactly one set of terms."
                        )
                    }
                )
        return data


class HrWorkScheduleSerializer(HrBaseSerializer):
    weekly_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = HrWorkSchedule
        fields = [
            "id",
            "profile",
            "name",
            "valid_from",
            "valid_to",
            "monday_minutes",
            "tuesday_minutes",
            "wednesday_minutes",
            "thursday_minutes",
            "friday_minutes",
            "saturday_minutes",
            "sunday_minutes",
            "is_flexible",
            "notional_daily_minutes",
            "weekly_minutes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["workspace", "created_at", "updated_at"]


class HrHolidayCalendarSerializer(HrBaseSerializer):
    class Meta:
        model = HrHolidayCalendar
        fields = [
            "id",
            "name",
            "country_code",
            "region_code",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["workspace", "created_at", "updated_at"]


class HrHolidaySerializer(HrBaseSerializer):
    class Meta:
        model = HrHoliday
        fields = [
            "id",
            "calendar",
            "date",
            "name_de",
            "name_en",
            "day_fraction",
            "is_statutory",
        ]
        read_only_fields = ["workspace"]


class HrAbsenceTypeSerializer(HrBaseSerializer):
    class Meta:
        model = HrAbsenceType
        fields = [
            "id",
            "code",
            "name_de",
            "name_en",
            "credits_actual",
            "consumes_leave_entitlement",
            "consumes_balance",
            "is_paid",
            "requires_approval",
            "requires_document",
            "max_consecutive_days",
            "colour",
            "is_active",
        ]
        read_only_fields = ["workspace"]


class HrAbsenceSerializer(HrBaseSerializer):
    absence_type_code = serializers.CharField(source="absence_type.code", read_only=True)
    absence_type_name = serializers.CharField(source="absence_type.name_de", read_only=True)

    class Meta:
        model = HrAbsence
        fields = [
            "id",
            "profile",
            "absence_type",
            "absence_type_code",
            "absence_type_name",
            "start_date",
            "end_date",
            "granularity",
            "start_half",
            "end_half",
            "minutes_per_day",
            "total_minutes",
            "state",
            "approved_by",
            "approved_at",
            "reason",
            "rejection_reason",
            "locked_period",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "workspace",
            "profile",
            "total_minutes",
            "approved_by",
            "approved_at",
            "locked_period",
            "created_at",
            "updated_at",
        ]

    def validate(self, data):
        start = data.get("start_date", getattr(self.instance, "start_date", None))
        end = data.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "The end cannot fall before the start."})
        granularity = data.get("granularity", getattr(self.instance, "granularity", None))
        minutes = data.get("minutes_per_day", getattr(self.instance, "minutes_per_day", None))
        if granularity == HrAbsence.Granularity.HOURS and not minutes:
            raise serializers.ValidationError(
                {"minutes_per_day": "Say how many minutes a day this absence covers."}
            )
        return data


class HrTeamAbsenceSerializer(serializers.ModelSerializer):
    """What colleagues may see of each other's absence: that it happened, not why.

    Deliberately its own serializer rather than a filtered version of the full one.
    An absence type can imply a medical reason, so this carries the dates and the
    person and nothing else — and being a separate class means a field added to the
    full serializer later cannot silently appear here.
    """

    member_display_name = serializers.CharField(source="profile.member.display_name", read_only=True)

    class Meta:
        model = HrAbsence
        fields = ["id", "profile", "member_display_name", "start_date", "end_date", "granularity"]
        read_only_fields = fields


class HrTimeEntrySerializer(HrBaseSerializer):
    class Meta:
        model = HrTimeEntry
        fields = [
            "id",
            "profile",
            "entry_date",
            "minutes",
            "category",
            "source",
            "project",
            "import_batch",
            "locked_period",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "workspace",
            "profile",
            "source",
            "import_batch",
            "locked_period",
            "created_at",
            "updated_at",
        ]

    def validate_minutes(self, value):
        if value == 0:
            raise serializers.ValidationError("An entry of no time is not a record of anything.")
        if abs(value) > 1440:
            raise serializers.ValidationError("A single day cannot hold more than 24 hours.")
        return value


class HrAttendanceDaySerializer(HrBaseSerializer):
    class Meta:
        model = HrAttendanceDay
        fields = [
            "id",
            "profile",
            "work_date",
            "started_at_local",
            "ended_at_local",
            "local_timezone",
            "break_minutes",
            "crosses_midnight",
            "net_minutes",
            "recording_method",
            "note",
            "locked_period",
        ]
        read_only_fields = ["workspace", "profile", "net_minutes", "locked_period"]


class HrLeaveEntitlementSerializer(HrBaseSerializer):
    granted_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = HrLeaveEntitlement
        fields = [
            "id",
            "profile",
            "leave_year_start",
            "leave_year_end",
            "entitlement_minutes",
            "carryover_minutes",
            "adjustment_minutes",
            "granted_minutes",
            "expires_on",
            "basis_note",
            "is_final",
        ]
        read_only_fields = ["workspace", "profile"]


class HrPeriodDaySerializer(HrBaseSerializer):
    class Meta:
        model = HrPeriodDay
        fields = [
            "id",
            "work_date",
            "target_minutes",
            "project_minutes",
            "non_project_minutes",
            "attendance_minutes",
            "absence_minutes",
            "holiday_minutes",
            "actual_minutes",
            "balance_minutes",
            "day_kind",
            "needs_review",
            "note",
            "last_rebuilt_at",
        ]
        read_only_fields = fields


class HrPeriodSerializer(HrBaseSerializer):
    member_display_name = serializers.CharField(source="profile.member.display_name", read_only=True)

    class Meta:
        model = HrPeriod
        fields = [
            "id",
            "profile",
            "member_display_name",
            "period_start",
            "period_end",
            "state",
            "target_minutes",
            "actual_minutes",
            "balance_minutes",
            "opening_balance_minutes",
            "closing_balance_minutes",
            "project_minutes",
            "non_project_minutes",
            "attendance_minutes",
            "absence_minutes",
            "holiday_minutes",
            "leave_consumed_minutes",
            "balance_consumed_minutes",
            "overtime_minutes",
            "computation_version",
            "submitted_at",
            "approved_at",
            "locked_at",
            "reopened_at",
            "reopen_reason",
        ]
        read_only_fields = fields
