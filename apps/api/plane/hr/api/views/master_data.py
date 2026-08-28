# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Setting up who works when, and which days nobody does.

Everything here is manager-only. Changing a schedule or a holiday moves the target
for months that are still open, which is why the endpoints refuse to touch
anything a closed month depends on.
"""

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.views.base import BaseAPIView
from plane.db.models import Workspace
from plane.hr.api.serializers.records import (
    HrAbsenceTypeSerializer,
    HrContractSerializer,
    HrEmploymentProfileSerializer,
    HrHolidayCalendarSerializer,
    HrHolidaySerializer,
    HrLeaveEntitlementSerializer,
    HrWorkScheduleSerializer,
)
from plane.hr.api.views.base import HrWorkspaceConfigEndpoint
from plane.hr.models import (
    HrAbsenceType,
    HrContract,
    HrEmploymentProfile,
    HrHoliday,
    HrHolidayCalendar,
    HrLeaveEntitlement,
    HrPeriod,
    HrWorkSchedule,
)
from plane.hr.permissions import (
    MANAGER,
    SELF,
    hr_permission,
    readable_profile_or_none,
    visible_profiles,
)


class HrEmploymentProfileEndpoint(HrWorkspaceConfigEndpoint):
    """The people the module knows about."""

    model = HrEmploymentProfile
    serializer_class = HrEmploymentProfileSerializer
    filter_fields = ("is_active", "member")

    def get_queryset(self, slug):
        return super().get_queryset(slug).select_related("member")

    @hr_permission(SELF)
    def get(self, request, slug, pk=None):
        # Reading a person is the one thing here that is not manager-only: you can
        # always read your own record.
        rows = visible_profiles(request, slug).select_related("member")
        if pk is not None:
            row = rows.filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(self.serializer_class(row).data, status=status.HTTP_200_OK)
        rows = self._apply_filters(rows, request)
        return Response(self.serializer_class(rows, many=True).data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def delete(self, request, slug, pk):
        # An employment record is not deleted when somebody leaves — the months
        # they worked still have to be readable. It is marked inactive instead.
        row = self.get_queryset(slug).filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        row.is_active = False
        row.save()
        return Response(self.serializer_class(row).data, status=status.HTTP_200_OK)


class HrContractEndpoint(BaseAPIView):
    """Somebody's terms, as a series of dated slices."""

    @hr_permission(SELF)
    def get(self, request, slug, profile_id, pk=None):
        profile = readable_profile_or_none(request, slug, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        rows = HrContract.objects.filter(profile_id=profile.id)
        if pk is not None:
            row = rows.filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(HrContractSerializer(row).data, status=status.HTTP_200_OK)
        return Response(HrContractSerializer(rows, many=True).data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def post(self, request, slug, profile_id):
        profile = readable_profile_or_none(request, slug, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = HrContractSerializer(data=request.data, context={"profile": profile})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(workspace_id=profile.workspace_id, profile=profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @hr_permission(MANAGER)
    def patch(self, request, slug, profile_id, pk):
        profile = readable_profile_or_none(request, slug, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        row = HrContract.objects.filter(profile_id=profile.id, pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = HrContractSerializer(
            row, data=request.data, partial=True, context={"profile": profile}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def delete(self, request, slug, profile_id, pk):
        profile = readable_profile_or_none(request, slug, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        row = HrContract.objects.filter(profile_id=profile.id, pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if _overlaps_a_closed_month(profile, row.valid_from, row.valid_to):
            return Response(
                {
                    "error": (
                        "A closed month was worked out against these terms. Reopen "
                        "the month first if they genuinely need to change."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _overlaps_a_closed_month(profile, valid_from, valid_to):
    """Whether a dated slice covers any month that has already been closed."""
    periods = HrPeriod.objects.filter(
        profile_id=profile.id,
        state=HrPeriod.State.LOCKED,
        period_end__gte=valid_from,
    )
    if valid_to is not None:
        periods = periods.filter(period_start__lte=valid_to)
    return periods.exists()


class HrWorkScheduleEndpoint(HrWorkspaceConfigEndpoint):
    """Expected hours per weekday, company-wide or for one person."""

    model = HrWorkSchedule
    serializer_class = HrWorkScheduleSerializer
    filter_fields = ("profile",)

    @hr_permission(MANAGER)
    def delete(self, request, slug, pk):
        row = self.get_queryset(slug).filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.profile_id and _overlaps_a_closed_month(row.profile, row.valid_from, row.valid_to):
            return Response(
                {"error": "A closed month was worked out against this schedule."},
                status=status.HTTP_409_CONFLICT,
            )
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HrHolidayCalendarEndpoint(HrWorkspaceConfigEndpoint):
    model = HrHolidayCalendar
    serializer_class = HrHolidayCalendarSerializer
    filter_fields = ("country_code", "is_default")
    # Everybody needs to know which days are holidays.
    read_requires_manager = False


class HrHolidayEndpoint(HrWorkspaceConfigEndpoint):
    model = HrHoliday
    serializer_class = HrHolidaySerializer
    filter_fields = ("calendar",)
    read_requires_manager = False

    def get_queryset(self, slug):
        return super().get_queryset(slug).select_related("calendar")

    @hr_permission(SELF)
    def get(self, request, slug, pk=None):
        rows = self._apply_filters(self.get_queryset(slug), request)
        year = request.query_params.get("year")
        if year and year.isdigit():
            rows = rows.filter(date__year=int(year))
        if pk is not None:
            row = rows.filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(self.serializer_class(row).data, status=status.HTTP_200_OK)
        return Response(
            self.serializer_class(rows.order_by("date"), many=True).data, status=status.HTTP_200_OK
        )


class HrAbsenceTypeEndpoint(HrWorkspaceConfigEndpoint):
    model = HrAbsenceType
    serializer_class = HrAbsenceTypeSerializer
    filter_fields = ("is_active",)
    # People need the list to request an absence at all.
    read_requires_manager = False


class HrLeaveEntitlementEndpoint(BaseAPIView):
    """How much leave somebody has for a leave year."""

    @hr_permission(SELF)
    def get(self, request, slug, profile_id):
        profile = readable_profile_or_none(request, slug, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        rows = HrLeaveEntitlement.objects.filter(profile_id=profile.id)
        return Response(HrLeaveEntitlementSerializer(rows, many=True).data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def post(self, request, slug, profile_id):
        profile = readable_profile_or_none(request, slug, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = HrLeaveEntitlementSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(workspace_id=profile.workspace_id, profile=profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @hr_permission(MANAGER)
    def patch(self, request, slug, profile_id, pk):
        profile = readable_profile_or_none(request, slug, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        row = HrLeaveEntitlement.objects.filter(profile_id=profile.id, pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.is_final:
            return Response(
                {
                    "error": (
                        "This entitlement has been agreed with the person. Record a "
                        "further adjustment rather than editing what was agreed."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        serializer = HrLeaveEntitlementSerializer(row, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class HrWorkspaceBootstrapEndpoint(BaseAPIView):
    """Create the records a workspace needs before anybody can be set up.

    Doing this by hand means eight forms before the first useful screen, and the
    company-wide schedule is the sort of thing that gets filled in wrong once and
    then quietly underpins every figure afterwards.
    """

    @hr_permission(MANAGER)
    def post(self, request, slug):
        workspace = Workspace.objects.filter(slug=slug).first()
        if workspace is None:
            return Response({"error": "No such workspace."}, status=status.HTTP_404_NOT_FOUND)

        created = {}
        if not HrAbsenceType.objects.filter(workspace=workspace).exists():
            HrAbsenceType.objects.bulk_create(
                [
                    HrAbsenceType(
                        workspace=workspace,
                        code=code,
                        name_de=name_de,
                        name_en=name_en,
                        credits_actual=credits,
                        consumes_leave_entitlement=leave,
                        consumes_balance=balance,
                        requires_document=document,
                        precedence=precedence,
                    )
                    for code, name_de, name_en, credits, leave, balance, document, precedence in (
                        ("urlaub", "Urlaub", "Annual leave", True, True, False, False, 100),
                        # Sickness outranks leave, so a day taken ill during booked
                        # leave is charged to sickness and the leave stays.
                        ("krankenstand", "Krankenstand", "Sick leave", True, False, False, True, 10),
                        ("zeitausgleich", "Zeitausgleich", "Time off in lieu", True, False, True, False, 50),
                        (
                            "pflegefreistellung",
                            "Pflegefreistellung",
                            "Care leave",
                            True,
                            False,
                            False,
                            False,
                            20,
                        ),
                        (
                            "dienstverhinderung",
                            "Sonstige Dienstverhinderung",
                            "Other justified absence",
                            True,
                            False,
                            False,
                            False,
                            30,
                        ),
                        ("unbezahlt", "Unbezahlter Urlaub", "Unpaid leave", False, False, False, False, 200),
                    )
                ]
            )
            created["absence_types"] = HrAbsenceType.objects.filter(workspace=workspace).count()

        if not HrHolidayCalendar.objects.filter(workspace=workspace).exists():
            HrHolidayCalendar.objects.create(
                workspace=workspace, name="Österreich", country_code="AT", is_default=True
            )
            created["holiday_calendar"] = "AT"

        if not HrWorkSchedule.objects.filter(workspace=workspace, profile__isnull=True).exists():
            # The collective agreement week rather than forty hours, because that
            # is what applies here and a wrong default is worse than none.
            HrWorkSchedule.objects.create(
                workspace=workspace,
                name="Standard",
                valid_from=request.data.get("valid_from") or "2020-01-01",
                monday_minutes=462,
                tuesday_minutes=462,
                wednesday_minutes=462,
                thursday_minutes=462,
                friday_minutes=462,
            )
            created["default_schedule"] = "38.5h week over five days"

        return Response(
            {"created": created, "already_present": not created},
            status=status.HTTP_200_OK,
        )
