# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rates, and the monthly invoices some people send for their own hours.

These rates are internal — what an hour of somebody's time costs the company. They
are deliberately not the rates the customer is billed at, which live in the CRM and
stay there. Nothing in this file is ever sent anywhere.

The point of holding an invoice here is not filing. It is that the module already
knows how many hours were agreed for the month, so it can say what the invoice is
expected to come to and point out when it does not — which catches a mistake about
money rather than merely reporting a number.
"""

# Django imports
from django.db import models

# Module imports
from plane.hr.models.base import HrBaseModel


class HrRateCard(HrBaseModel):
    """What an hour costs, for a stretch of time."""

    class Basis(models.IntegerChoices):
        HOURLY = 10, "Per hour"
        MONTHLY_FIXED = 20, "Fixed monthly amount"
        MONTHLY_PLUS_OVERTIME = 30, "Monthly amount plus overtime"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_rate_cards",
    )
    # Null means the workspace default.
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rate_cards",
    )
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    currency = models.CharField(max_length=3, default="EUR")
    basis = models.PositiveSmallIntegerField(choices=Basis.choices, default=Basis.HOURLY)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    monthly_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    overtime_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.5)
    holiday_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=2)

    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_vat_exempt = models.BooleanField(default=False)
    vat_exemption_note = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        owner = self.profile_id or "workspace default"
        return f"{owner} from {self.valid_from}"

    class Meta:
        verbose_name = "HR Rate Card"
        verbose_name_plural = "HR Rate Cards"
        db_table = "hr_rate_cards"
        ordering = ("-valid_from",)
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "valid_from"],
                condition=models.Q(profile__isnull=False),
                name="unique_hr_rate_start_per_profile",
            ),
            models.UniqueConstraint(
                fields=["workspace", "valid_from"],
                condition=models.Q(profile__isnull=True),
                name="unique_hr_default_rate_start",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=models.F("valid_from")),
                name="hr_rate_valid_range",
            ),
        ]
        indexes = [models.Index(fields=["profile", "valid_from", "valid_to"])]


class HrInvoiceDocument(HrBaseModel):
    """A monthly invoice from somebody who bills for their own hours."""

    class ReconciliationState(models.IntegerChoices):
        PENDING = 10, "Not yet checked"
        MATCHED = 20, "Matches the approved hours"
        VARIANCE_ACCEPTED = 30, "Differs, and that was accepted"
        DISPUTED = 40, "Disputed"
        WAIVED = 50, "Not applicable"

    class PaymentState(models.IntegerChoices):
        UNPAID = 10, "Unpaid"
        SCHEDULED = 20, "Scheduled"
        PAID = 30, "Paid"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_invoice_documents",
    )
    # Neither the person nor the month can be removed on its own while an invoice
    # refers to it. RESTRICT rather than PROTECT, so that deleting the whole
    # workspace still works — the invoice is going too, and there is nothing left
    # to protect. PROTECT would refuse, and since the shared retention task deletes
    # workspaces outright it would take that task down for every workspace at once.
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.RESTRICT,
        related_name="invoice_documents",
    )
    period = models.ForeignKey(
        "hr.HrPeriod",
        on_delete=models.RESTRICT,
        related_name="invoice_documents",
    )

    document_number = models.CharField(max_length=64, blank=True, default="")
    document_date = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    currency = models.CharField(max_length=3, default="EUR")
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # What the invoice says, what the closed month says, and the gap between them.
    claimed_minutes = models.IntegerField(null=True, blank=True)
    reconciled_minutes = models.IntegerField(null=True, blank=True)
    variance_minutes = models.IntegerField(null=True, blank=True)
    reconciliation_state = models.PositiveSmallIntegerField(
        choices=ReconciliationState.choices,
        default=ReconciliationState.PENDING,
    )
    reconciled_by = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_reconciled_invoices",
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)
    variance_note = models.TextField(blank=True, default="")

    asset = models.ForeignKey(
        "db.FileAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_invoice_documents",
    )
    payment_state = models.PositiveSmallIntegerField(
        choices=PaymentState.choices,
        default=PaymentState.UNPAID,
    )
    paid_on = models.DateField(null=True, blank=True)
    # A correction is a credit note against the original, not an edit of it.
    credit_note_for = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_notes",
    )

    def __str__(self):
        return f"{self.profile_id} {self.document_number or self.id}"

    class Meta:
        verbose_name = "HR Invoice Document"
        verbose_name_plural = "HR Invoice Documents"
        db_table = "hr_invoice_documents"
        ordering = ("-document_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "period"],
                condition=models.Q(credit_note_for__isnull=True),
                name="unique_hr_invoice_per_period",
            )
        ]
        indexes = [models.Index(fields=["workspace", "reconciliation_state"])]
