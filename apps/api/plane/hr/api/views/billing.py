# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rates, the statement that goes out before an invoice, and checking the invoice."""

# Django imports
from django.utils import timezone

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.views.base import BaseAPIView
from plane.hr.api.serializers.billing import HrInvoiceDocumentSerializer, HrRateCardSerializer
from plane.hr.api.views.base import HrWorkspaceConfigEndpoint
from plane.hr.models import HrInvoiceDocument, HrPeriod, HrRateCard
from plane.hr.services.refusal import Refused
from plane.hr.permissions import (
    MANAGER,
    SELF,
    hr_permission,
    readable_profile_or_none,
    visible_profiles,
)
from plane.hr.services import billing


class HrRateCardEndpoint(HrWorkspaceConfigEndpoint):
    """What an hour of somebody's time costs the company.

    Manager-only in both directions. These are internal cost rates, and there is
    no reason for one person to be able to read another's.
    """

    model = HrRateCard
    serializer_class = HrRateCardSerializer
    filter_fields = ("profile",)


class HrStatementEndpoint(BaseAPIView):
    """What a month is worth, sent before the invoice is written rather than after."""

    @hr_permission(SELF)
    def get(self, request, pk):
        period = (
            HrPeriod.objects.filter(pk=pk, profile__in=visible_profiles(request))
            .select_related("profile__member", "profile__workspace")
            .first()
        )
        if period is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(billing.statement_for(period), status=status.HTTP_200_OK)


class HrInvoiceEndpoint(BaseAPIView):
    """The invoice somebody sends for their own hours."""

    def _visible(self, request):
        return HrInvoiceDocument.objects.filter(profile__in=visible_profiles(request)).select_related(
            "profile__member", "period"
        )

    @hr_permission(SELF)
    def get(self, request, pk=None):
        rows = self._visible(request)
        if pk is not None:
            row = rows.filter(pk=pk).first()
            if row is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(HrInvoiceDocumentSerializer(row).data, status=status.HTTP_200_OK)

        profile_id = request.query_params.get("profile_id")
        if profile_id:
            rows = rows.filter(profile_id=profile_id)
        year = request.query_params.get("year")
        if year and year.isdigit():
            rows = rows.filter(period__period_start__year=int(year))
        return Response(
            HrInvoiceDocumentSerializer(rows.order_by("-document_date"), many=True).data,
            status=status.HTTP_200_OK,
        )

    @hr_permission(SELF)
    def post(self, request):
        profile = readable_profile_or_none(request, request.data.get("profile_id"))
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        period = HrPeriod.objects.filter(pk=request.data.get("period"), profile_id=profile.id).first()
        if period is None:
            return Response(
                {"error": "Say which month this invoice is for."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = HrInvoiceDocumentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        invoice = serializer.save(
            workspace_id=profile.workspace_id,
            profile=profile,
            period=period,
            received_at=timezone.now(),
        )
        return Response(HrInvoiceDocumentSerializer(invoice).data, status=status.HTTP_201_CREATED)

    @hr_permission(SELF)
    def patch(self, request, pk):
        row = self._visible(request).filter(pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not request.hr_is_manager and row.reconciliation_state != HrInvoiceDocument.ReconciliationState.PENDING:
            return Response(
                {"error": "This invoice has already been looked at. Ask for it to be changed."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = HrInvoiceDocumentSerializer(row, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class HrInvoiceReconcileEndpoint(BaseAPIView):
    """Check an invoice against the month it is for."""

    @hr_permission(MANAGER)
    def post(self, request, pk):
        invoice = (
            HrInvoiceDocument.objects.filter(pk=pk, profile__in=visible_profiles(request))
            .select_related("period")
            .first()
        )
        if invoice is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            billing.reconcile(invoice)
        except Refused as refused:
            return Response({"error": refused.message}, status=status.HTTP_409_CONFLICT)
        invoice.reconciled_by = request.user
        invoice.reconciled_at = timezone.now()
        invoice.save()
        return Response(HrInvoiceDocumentSerializer(invoice).data, status=status.HTTP_200_OK)


class HrInvoiceAcceptVarianceEndpoint(BaseAPIView):
    """Accept an invoice that does not match, with the reason recorded."""

    @hr_permission(MANAGER)
    def post(self, request, pk):
        invoice = HrInvoiceDocument.objects.filter(pk=pk, profile__in=visible_profiles(request)).first()
        if invoice is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        note = (request.data.get("note") or "").strip()
        if not note:
            # Accepting a difference without saying why turns the check into a
            # button somebody presses to make the warning go away.
            return Response(
                {"error": "Say why the difference is being accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice.reconciliation_state = HrInvoiceDocument.ReconciliationState.VARIANCE_ACCEPTED
        invoice.variance_note = note
        invoice.reconciled_by = request.user
        invoice.reconciled_at = timezone.now()
        invoice.save()
        return Response(HrInvoiceDocumentSerializer(invoice).data, status=status.HTTP_200_OK)
