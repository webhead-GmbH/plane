# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Setting up who works when, and which days nobody does.

Everything here is manager-only. Changing a schedule or a holiday moves the target
for months that are still open, which is why the endpoints refuse to touch
anything a closed month depends on.
"""

# Django imports
from django.utils import timezone

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.views.base import BaseAPIView
from plane.hr.api.serializers.records import (
    HrAbsenceTypeSerializer,
    HrContractSerializer,
    HrEmploymentProfileSerializer,
    HrHolidayCalendarSerializer,
    HrHolidaySerializer,
    HrLeaveEntitlementSerializer,
    HrWorkScheduleSerializer,
)
from plane.db.models import User
from plane.hr.api.views.base import HrWorkspaceConfigEndpoint
from plane.hr.models import (
    HrAbsence,
    HrAbsenceType,
    HrContract,
    HrEmploymentProfile,
    HrHoliday,
    HrHolidayCalendar,
    HrLeaveEntitlement,
    HrPeriod,
    HrWorkSchedule,
)
from plane.hr.services.audit import record
from plane.hr.utils.company import hr_home_workspace
from plane.hr.utils.crm_link import set_crm_staff_id
from plane.hr.permissions import (
    MANAGER,
    SELF,
    hr_permission,
    readable_profile_or_none,
    visible_profiles,
)


class HrCandidateEndpoint(BaseAPIView):
    """People who could be given an employment record but do not have one.

    Drawn from workspace membership across the whole installation rather than
    from whichever workspace the manager happens to be looking at, because
    employment is with the company: somebody working only in another workspace
    is still a colleague who needs a month.
    """

    @hr_permission(MANAGER)
    def get(self, request):
        employed = HrEmploymentProfile.objects.values_list("member_id", flat=True)
        candidates = (
            User.objects.filter(
                member_workspace__is_active=True,
                is_active=True,
                # Bots hold workspace membership so they can act through the API.
                # Nobody is going to pay one, and offering them here would make
                # the list of colleagues something to read past rather than pick from.
                is_bot=False,
            )
            .exclude(id__in=employed)
            .distinct()
            .order_by("display_name", "email")
        )
        return Response(
            [
                {
                    "id": str(person.id),
                    "display_name": person.display_name or "",
                    "email": person.email or "",
                    "avatar_url": person.avatar_url or "",
                }
                for person in candidates
            ],
            status=status.HTTP_200_OK,
        )


class HrEmploymentProfileEndpoint(HrWorkspaceConfigEndpoint):
    """The people the module knows about."""

    model = HrEmploymentProfile
    serializer_class = HrEmploymentProfileSerializer
    filter_fields = ("is_active", "member")

    def get_queryset(self):
        return super().get_queryset().select_related("member")

    @hr_permission(SELF)
    def get(self, request, pk=None):
        # Reading a person is the one thing here that is not manager-only: you can
        # always read your own record.
        rows = visible_profiles(request).select_related("member")
        if pk is not None:
            row = rows.filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(self.serializer_class(row).data, status=status.HTTP_200_OK)
        rows = self._apply_filters(rows, request)
        return Response(self.serializer_class(rows, many=True).data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def patch(self, request, pk):
        """Change somebody's record, including who they are in the CRM.

        The staff id is not a field of this model — it belongs to the workspace
        membership — so it is taken out of the payload and written separately.
        An empty value clears it, which is how somebody is put back on the email
        match rather than being stuck with a wrong id forever.
        """
        row = self.get_queryset().filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        sets_crm = "crm_staff_id" in payload
        raw = payload.pop("crm_staff_id", None)
        if isinstance(raw, list):
            raw = raw[0] if raw else None

        if sets_crm:
            if raw in (None, "", "null"):
                staff_id = None
            else:
                try:
                    staff_id = int(raw)
                except (TypeError, ValueError):
                    return Response(
                        {"crm_staff_id": ["A CRM staff id is a whole number."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if staff_id <= 0:
                    return Response(
                        {"crm_staff_id": ["A CRM staff id is a whole number."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        serializer = self.serializer_class(row, data=payload, partial=True, context=self._serializer_context(request))
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        was_manager = row.is_hr_manager
        becomes_manager = serializer.validated_data.get("is_hr_manager", was_manager)
        stays_employed = serializer.validated_data.get("is_active", row.is_active)

        # Two different edits reach the same place. Taking the flag away is the
        # obvious one; marking the only person who holds it as having left is the
        # one that looks like an unrelated field. Both end with nobody able to
        # reach any month and nobody able to hand it back, because the endpoint
        # that would is itself manager-only.
        if was_manager and (not becomes_manager or not stays_employed) and not _another_manager_remains(row):
            return Response(_LAST_MANAGER, status=status.HTTP_409_CONFLICT)

        serializer.save()

        # After the record saves, so a rejected change does not leave the id moved.
        if sets_crm:
            set_crm_staff_id(row, staff_id)

        if was_manager != becomes_manager:
            # Filed like any other change to somebody's record, because it is one —
            # and the one with the widest reach. Without it the only trace that
            # somebody was handed every colleague's absences is the flag itself,
            # which says nothing about who did it or when.
            record(
                row,
                request.user,
                row,
                "hr_manager_granted" if becomes_manager else "hr_manager_withdrawn",
                {"is_hr_manager": {"from": was_manager, "to": becomes_manager}},
                request=request,
            )

        return Response(self.serializer_class(row).data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def delete(self, request, pk):
        # An employment record is not deleted when somebody leaves — the months
        # they worked still have to be readable. It is marked inactive instead.
        row = self.get_queryset().filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        # The third door to the same room. Marking the last manager as having
        # left closes the module behind them exactly as taking their flag away
        # would, and a guard on one door of three is not a guard.
        if row.is_hr_manager and not _another_manager_remains(row):
            return Response(_LAST_MANAGER, status=status.HTTP_409_CONFLICT)
        row.is_active = False
        row.save()
        return Response(self.serializer_class(row).data, status=status.HTTP_200_OK)


_LAST_MANAGER = {
    "error": (
        "This is the only person who looks after the team. Taking it away would "
        "leave nobody able to reach anyone's month, and nobody able to give it "
        "back. Make somebody else a manager first."
    ),
    "reason": "last_manager",
}


def _another_manager_remains(profile):
    """Whether anybody else would still look after the team without this person.

    Across the whole installation, because that is the scope the flag actually
    has — a manager in any workspace can reach every profile in all of them.

    Somebody has to be able to sign in to count as cover. An employment record
    stays active when the Plane account behind it is deactivated, and that person
    can no more look after the team than one who has left — which is the same
    reason the employment record's own ``is_active`` is checked.
    """
    return (
        HrEmploymentProfile.objects.filter(is_hr_manager=True, is_active=True, member__is_active=True)
        .exclude(pk=profile.pk)
        .exists()
    )


class HrContractEndpoint(BaseAPIView):
    """Somebody's terms, as a series of dated slices."""

    @hr_permission(SELF)
    def get(self, request, profile_id, pk=None):
        profile = readable_profile_or_none(request, profile_id)
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
    def post(self, request, profile_id):
        profile = readable_profile_or_none(request, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = HrContractSerializer(data=request.data, context={"profile": profile})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(workspace_id=profile.workspace_id, profile=profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @hr_permission(MANAGER)
    def patch(self, request, profile_id, pk):
        profile = readable_profile_or_none(request, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        row = HrContract.objects.filter(profile_id=profile.id, pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = HrContractSerializer(row, data=request.data, partial=True, context={"profile": profile})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        refusal = _refuse_if_a_closed_month_depends_on_it(
            profile,
            (row.valid_from, row.valid_to),
            (
                serializer.validated_data.get("valid_from", row.valid_from),
                serializer.validated_data.get("valid_to", row.valid_to),
            ),
            "terms",
        )
        if refusal:
            return Response(refusal, status=status.HTTP_409_CONFLICT)

        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def delete(self, request, profile_id, pk):
        profile = readable_profile_or_none(request, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        row = HrContract.objects.filter(profile_id=profile.id, pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if _overlaps_a_closed_month(profile, row.valid_from, row.valid_to):
            return Response({"error": _DEPENDS_ON["terms"]}, status=status.HTTP_409_CONFLICT)
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# What each kind of dated slice is called when a month has to be reopened to
# change it. The wording is the whole message: "this cannot be edited" without
# saying what to do about it leaves somebody stuck at a dialog.
_DEPENDS_ON = {
    "terms": (
        "A closed month was worked out against these terms. Reopen the month first if they genuinely need to change."
    ),
    "schedule": (
        "A closed month was worked out against this schedule. Reopen the month first if it genuinely needs to change."
    ),
}


def _refuse_if_a_closed_month_depends_on_it(profile, was, becomes, kind):
    """The refusal for editing a dated slice a closed month was built on, or None.

    Both the range it covers now and the range it would cover afterwards, because
    the two damaging edits are opposite: rewriting a slice a closed month already
    used, and dragging a slice that was harmless back over one. Deleting such a
    slice has been refused from the start; editing it was not, and an edit changes
    exactly the same thing — what the frozen figures say they were derived from,
    which is the one record that has to still explain them a year later.
    """
    if _overlaps_a_closed_month(profile, *was) or _overlaps_a_closed_month(profile, *becomes):
        return {"error": _DEPENDS_ON[kind]}
    return None


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
    def patch(self, request, pk):
        """The inherited edit, with the guard its own delete already had.

        A company-wide schedule has no profile, so there is nobody whose closed
        months it could be checked against — it is left to the base class, which
        is the honest answer rather than a check that silently passes.
        """
        row = self.get_queryset().filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.profile_id:
            serializer = self.serializer_class(
                row, data=request.data, partial=True, context=self._serializer_context(request)
            )
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            refusal = _refuse_if_a_closed_month_depends_on_it(
                row.profile,
                (row.valid_from, row.valid_to),
                (
                    serializer.validated_data.get("valid_from", row.valid_from),
                    serializer.validated_data.get("valid_to", row.valid_to),
                ),
                "schedule",
            )
            if refusal:
                return Response(refusal, status=status.HTTP_409_CONFLICT)
        return super().patch(request, pk)

    @hr_permission(MANAGER)
    def delete(self, request, pk):
        row = self.get_queryset().filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.profile_id and _overlaps_a_closed_month(row.profile, row.valid_from, row.valid_to):
            return Response({"error": _DEPENDS_ON["schedule"]}, status=status.HTTP_409_CONFLICT)
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

    def get_queryset(self):
        return super().get_queryset().select_related("calendar")

    @hr_permission(SELF)
    def get(self, request, pk=None):
        rows = self._apply_filters(self.get_queryset(), request)
        year = request.query_params.get("year")
        if year and year.isdigit():
            rows = rows.filter(date__year=int(year))
        if pk is not None:
            row = rows.filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(self.serializer_class(row).data, status=status.HTTP_200_OK)
        return Response(self.serializer_class(rows.order_by("date"), many=True).data, status=status.HTTP_200_OK)


class HrAbsenceTypeEndpoint(HrWorkspaceConfigEndpoint):
    model = HrAbsenceType
    serializer_class = HrAbsenceTypeSerializer
    filter_fields = ("is_active",)
    # People need the list to request an absence at all.
    read_requires_manager = False

    @hr_permission(MANAGER)
    def delete(self, request, pk):
        """Remove a kind of absence, unless something has been recorded as it.

        The database refuses that outright — an absence whose kind had been
        deleted would be a record nobody could read — and the refusal arrived as a
        database error, which the generic handler turns into "The payload is not
        valid". That is true of nothing here: the payload was fine and the request
        was reasonable, and the person reading it has no way to guess that the
        answer is to switch the type off instead of deleting it.
        """
        row = self.get_queryset().filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        recorded = HrAbsence.objects.filter(absence_type_id=row.id).count()
        if recorded:
            return Response(
                {
                    "error": (
                        "%d absence(s) are recorded as this kind, so it cannot be "
                        "removed — the record of them would stop making sense. "
                        "Switch it off instead: it disappears from the list of "
                        "kinds somebody can choose, and the existing ones stay "
                        "readable." % recorded
                    ),
                    # Named, so the screen can count in its own language. The
                    # sentence above stays as the fallback and as what a log shows.
                    "reason": "absence_type_in_use",
                    "in_use": recorded,
                },
                status=status.HTTP_409_CONFLICT,
            )

        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HrLeaveEntitlementEndpoint(BaseAPIView):
    """How much leave somebody has for a leave year."""

    @hr_permission(SELF)
    def get(self, request, profile_id):
        profile = readable_profile_or_none(request, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        rows = HrLeaveEntitlement.objects.filter(profile_id=profile.id)
        return Response(HrLeaveEntitlementSerializer(rows, many=True).data, status=status.HTTP_200_OK)

    @hr_permission(MANAGER)
    def post(self, request, profile_id):
        profile = readable_profile_or_none(request, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = HrLeaveEntitlementSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(workspace_id=profile.workspace_id, profile=profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @hr_permission(MANAGER)
    def patch(self, request, profile_id, pk):
        profile = readable_profile_or_none(request, profile_id)
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


def _seed_holidays(workspace, calendar, span=5):
    """Fill in the public holidays around now, leaving any already there alone.

    Idempotent, and safe to re-run to extend the range: a day somebody has edited
    or removed by hand is not put back, because the calendar is theirs to correct.
    """
    from plane.hr.utils.holidays import austrian_holidays

    if calendar.country_code != "AT":
        return 0

    this_year = timezone.now().year
    years = range(this_year - span, this_year + span + 1)
    known = set(HrHoliday.objects.filter(calendar=calendar).values_list("date", flat=True))

    fresh = [
        HrHoliday(
            workspace=workspace,
            calendar=calendar,
            date=day,
            name_de=name_de,
            name_en=name_en,
            day_fraction=fraction,
            is_statutory=is_statutory,
        )
        for year in years
        for day, name_de, name_en, fraction, is_statutory in austrian_holidays(year)
        if day not in known
    ]
    HrHoliday.objects.bulk_create(fresh)
    return len(fresh)


class HrSetupEndpoint(BaseAPIView):
    """Create the records a workspace needs before anybody can be set up.

    Doing this by hand means eight forms before the first useful screen, and the
    company-wide schedule is the sort of thing that gets filled in wrong once and
    then quietly underpins every figure afterwards.
    """

    @hr_permission(MANAGER)
    def post(self, request):
        workspace = hr_home_workspace()

        created = {}
        if not HrAbsenceType.objects.exists():
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
            created["absence_types"] = HrAbsenceType.objects.count()

        calendar = HrHolidayCalendar.objects.filter(is_default=True).first()
        if calendar is None:
            calendar = HrHolidayCalendar.objects.create(
                workspace=workspace, name="Österreich", country_code="AT", is_default=True
            )
            created["holiday_calendar"] = "AT"

        # An empty calendar is not a neutral starting point: every public holiday
        # would read as an ordinary working day and show as a full day's shortfall
        # against somebody who was legally off. Seeded generously either side of
        # now, because past months are entered by hand from the old records and a
        # year that runs out brings the same fault back silently.
        added = _seed_holidays(workspace, calendar)
        if added:
            created["holidays"] = added

        if not HrWorkSchedule.objects.filter(profile__isnull=True).exists():
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
