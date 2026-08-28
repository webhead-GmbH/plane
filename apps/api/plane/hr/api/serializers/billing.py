# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rates and invoices over the API."""

# Third-party imports
from rest_framework import serializers

# Module imports
from plane.hr.api.serializers.base import HrBaseSerializer
from plane.hr.models import HrInvoiceDocument, HrRateCard


class HrRateCardSerializer(HrBaseSerializer):
    class Meta:
        model = HrRateCard
        fields = [
            "id",
            "profile",
            "valid_from",
            "valid_to",
            "currency",
            "basis",
            "hourly_rate",
            "monthly_amount",
            "overtime_multiplier",
            "holiday_multiplier",
            "vat_rate",
            "is_vat_exempt",
            "vat_exemption_note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["workspace", "created_at", "updated_at"]

    def validate(self, data):
        basis = data.get("basis", getattr(self.instance, "basis", HrRateCard.Basis.HOURLY))
        hourly = data.get("hourly_rate", getattr(self.instance, "hourly_rate", None))
        monthly = data.get("monthly_amount", getattr(self.instance, "monthly_amount", None))

        if basis == HrRateCard.Basis.HOURLY and hourly is None:
            raise serializers.ValidationError(
                {"hourly_rate": "An hourly rate needs an hourly figure."}
            )
        if basis != HrRateCard.Basis.HOURLY and monthly is None:
            raise serializers.ValidationError(
                {"monthly_amount": "A monthly rate needs a monthly figure."}
            )

        valid_from = data.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_to = data.get("valid_to", getattr(self.instance, "valid_to", None))
        if valid_from and valid_to and valid_to < valid_from:
            raise serializers.ValidationError({"valid_to": "The end cannot fall before the start."})
        return data


class HrInvoiceDocumentSerializer(HrBaseSerializer):
    member_display_name = serializers.CharField(source="profile.member.display_name", read_only=True)
    period_start = serializers.DateField(source="period.period_start", read_only=True)

    class Meta:
        model = HrInvoiceDocument
        fields = [
            "id",
            "profile",
            "member_display_name",
            "period",
            "period_start",
            "document_number",
            "document_date",
            "received_at",
            "currency",
            "net_amount",
            "vat_amount",
            "gross_amount",
            "claimed_minutes",
            "reconciled_minutes",
            "variance_minutes",
            "reconciliation_state",
            "reconciled_by",
            "reconciled_at",
            "variance_note",
            "asset",
            "payment_state",
            "paid_on",
            "credit_note_for",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "workspace",
            "profile",
            "period",
            "received_at",
            # Everything about whether the invoice agrees with the month is worked
            # out here, never taken from what was sent.
            "reconciled_minutes",
            "variance_minutes",
            "reconciliation_state",
            "reconciled_by",
            "reconciled_at",
            "created_at",
            "updated_at",
        ]
