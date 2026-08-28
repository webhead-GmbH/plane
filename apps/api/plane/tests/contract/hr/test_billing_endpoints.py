# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rates, the statement sent before an invoice, and checking the invoice."""

# Python imports
from datetime import date
from decimal import Decimal
from uuid import uuid4

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import (
    HrContract,
    HrEmploymentProfile,
    HrInvoiceDocument,
    HrPeriod,
    HrRateCard,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.hr.services.ledger import rebuild_period
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

FULL = 462


def new_user():
    return UserFactory(username=uuid4().hex)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def url(workspace, path):
    return f"/api/hr/workspaces/{workspace.slug}/{path}"


@pytest.fixture
def workspace():
    owner = new_user()
    workspace = WorkspaceFactory(owner=owner)
    WorkspaceMemberFactory(workspace=workspace, member=owner, role=ROLE.ADMIN.value)
    return workspace


def employ(workspace, is_hr_manager=False, self_invoicing=True):
    user = new_user()
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.MEMBER.value)
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone="Europe/Vienna",
        hire_date=date(2024, 1, 1),
        is_hr_manager=is_hr_manager,
    )
    HrContract.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2024, 1, 1),
        arrangement=(
            HrContract.Arrangement.REMOTE_FULL_TIME_INVOICING
            if self_invoicing
            else HrContract.Arrangement.ONSITE_FULL_TIME
        ),
        records_target_hours=not self_invoicing,
    )
    HrWorkSchedule.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2024, 1, 1),
        monday_minutes=FULL,
        tuesday_minutes=FULL,
        wednesday_minutes=FULL,
        thursday_minutes=FULL,
        friday_minutes=FULL,
    )
    return user, profile


@pytest.fixture
def manager(workspace):
    user, _ = employ(workspace, is_hr_manager=True, self_invoicing=False)
    return user


def march_for(profile, minutes=0):
    if minutes:
        HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=date(2026, 3, 2),
            minutes=minutes,
        )
    rebuild_period(profile, 2026, 3)
    return HrPeriod.objects.get(profile=profile, period_start=date(2026, 3, 1))


class TestRates:
    def test_a_manager_can_set_an_hourly_rate(self, workspace, manager):
        _, profile = employ(workspace)
        response = client_for(manager).post(
            url(workspace, "rate-cards/"),
            {
                "profile": str(profile.id),
                "valid_from": "2024-01-01",
                "basis": HrRateCard.Basis.HOURLY,
                "hourly_rate": "75.00",
            },
            format="json",
        )
        assert response.status_code == 201

    def test_an_hourly_rate_without_a_figure_is_refused(self, workspace, manager):
        _, profile = employ(workspace)
        response = client_for(manager).post(
            url(workspace, "rate-cards/"),
            {
                "profile": str(profile.id),
                "valid_from": "2024-01-01",
                "basis": HrRateCard.Basis.HOURLY,
            },
            format="json",
        )
        assert response.status_code == 400
        assert "hourly_rate" in response.json()

    def test_one_person_cannot_read_the_rates(self, workspace):
        # Internal cost rates. There is no reason for one person to see another's,
        # and no reason for them to see their own here either.
        user, _ = employ(workspace)
        assert client_for(user).get(url(workspace, "rate-cards/")).status_code == 403


class TestStatement:
    def test_it_says_what_the_month_is_worth(self, workspace, manager):
        _, profile = employ(workspace)
        HrRateCard.objects.create(
            workspace=workspace,
            profile=profile,
            valid_from=date(2024, 1, 1),
            basis=HrRateCard.Basis.HOURLY,
            hourly_rate=Decimal("75.00"),
        )
        period = march_for(profile, minutes=600)  # ten hours
        response = client_for(manager).get(url(workspace, f"periods/{period.id}/statement/"))
        assert response.status_code == 200
        body = response.json()
        assert body["minutes"] == 600
        assert body["hours"] == "10.00"
        assert body["expected_amount"] == "750.00"

    def test_the_person_can_see_their_own_before_they_invoice(self, workspace):
        # The useful moment is before the invoice is written, not after.
        user, profile = employ(workspace)
        HrRateCard.objects.create(
            workspace=workspace,
            profile=profile,
            valid_from=date(2024, 1, 1),
            basis=HrRateCard.Basis.HOURLY,
            hourly_rate=Decimal("60.00"),
        )
        period = march_for(profile, minutes=90)
        response = client_for(user).get(url(workspace, f"periods/{period.id}/statement/"))
        assert response.status_code == 200
        assert response.json()["expected_amount"] == "90.00"

    def test_an_open_month_says_so(self, workspace):
        user, profile = employ(workspace)
        period = march_for(profile, minutes=60)
        body = client_for(user).get(url(workspace, f"periods/{period.id}/statement/")).json()
        assert body["is_final"] is False

    def test_a_month_with_no_rate_says_so_rather_than_guessing(self, workspace):
        user, profile = employ(workspace)
        period = march_for(profile, minutes=60)
        body = client_for(user).get(url(workspace, f"periods/{period.id}/statement/")).json()
        assert body["has_rate"] is False
        assert body["expected_amount"] is None

    def test_a_workspace_rate_applies_to_somebody_with_none_of_their_own(self, workspace):
        user, profile = employ(workspace)
        HrRateCard.objects.create(
            workspace=workspace,
            profile=None,
            valid_from=date(2024, 1, 1),
            basis=HrRateCard.Basis.HOURLY,
            hourly_rate=Decimal("50.00"),
        )
        period = march_for(profile, minutes=120)
        body = client_for(user).get(url(workspace, f"periods/{period.id}/statement/")).json()
        assert body["expected_amount"] == "100.00"

    def test_one_person_cannot_read_anothers_statement(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        period = march_for(colleague, minutes=60)
        response = client_for(user).get(url(workspace, f"periods/{period.id}/statement/"))
        assert response.status_code == 404


class TestInvoices:
    def _closed_march(self, workspace, profile, minutes):
        period = march_for(profile, minutes=minutes)
        period.state = HrPeriod.State.LOCKED
        period.target_minutes = 0
        period.actual_minutes = minutes
        period.balance_minutes = minutes
        period.save()
        return period

    def test_somebody_can_send_their_own_invoice(self, workspace):
        user, profile = employ(workspace)
        period = march_for(profile, minutes=600)
        response = client_for(user).post(
            url(workspace, "invoices/"),
            {
                "profile_id": str(profile.id),
                "period": str(period.id),
                "document_number": "2026-03",
                "document_date": "2026-04-02",
                "claimed_minutes": 600,
                "net_amount": "750.00",
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["reconciliation_state"] == HrInvoiceDocument.ReconciliationState.PENDING

    def test_an_invoice_that_matches_is_marked_as_matching(self, workspace, manager):
        _, profile = employ(workspace)
        period = self._closed_march(workspace, profile, 600)
        invoice = HrInvoiceDocument.objects.create(
            workspace=workspace, profile=profile, period=period, claimed_minutes=600
        )
        response = client_for(manager).post(url(workspace, f"invoices/{invoice.id}/reconcile/"))
        assert response.status_code == 200
        body = response.json()
        assert body["reconciled_minutes"] == 600
        assert body["variance_minutes"] == 0
        assert body["reconciliation_state"] == HrInvoiceDocument.ReconciliationState.MATCHED

    def test_an_invoice_claiming_more_than_the_month_is_disputed(self, workspace, manager):
        # The point of holding the invoice at all: catching a mistake about money,
        # rather than reporting a number.
        _, profile = employ(workspace)
        period = self._closed_march(workspace, profile, 600)
        invoice = HrInvoiceDocument.objects.create(
            workspace=workspace, profile=profile, period=period, claimed_minutes=720
        )
        body = client_for(manager).post(
            url(workspace, f"invoices/{invoice.id}/reconcile/")
        ).json()
        assert body["variance_minutes"] == 120
        assert body["reconciliation_state"] == HrInvoiceDocument.ReconciliationState.DISPUTED

    def test_an_invoice_cannot_be_checked_against_a_month_that_can_still_move(
        self, workspace, manager
    ):
        # A variance that disappears on its own is worse than no check: somebody
        # would learn to ignore it.
        _, profile = employ(workspace)
        period = march_for(profile, minutes=600)
        invoice = HrInvoiceDocument.objects.create(
            workspace=workspace, profile=profile, period=period, claimed_minutes=600
        )
        response = client_for(manager).post(url(workspace, f"invoices/{invoice.id}/reconcile/"))
        assert response.status_code == 409

    def test_accepting_a_difference_requires_saying_why(self, workspace, manager):
        _, profile = employ(workspace)
        period = self._closed_march(workspace, profile, 600)
        invoice = HrInvoiceDocument.objects.create(
            workspace=workspace, profile=profile, period=period, claimed_minutes=720
        )
        client = client_for(manager)
        assert client.post(
            url(workspace, f"invoices/{invoice.id}/accept-variance/")
        ).status_code == 400
        ok = client.post(
            url(workspace, f"invoices/{invoice.id}/accept-variance/"),
            {"note": "Agreed to include the two hours of handover."},
            format="json",
        )
        assert ok.status_code == 200
        assert ok.json()["reconciliation_state"] == (
            HrInvoiceDocument.ReconciliationState.VARIANCE_ACCEPTED
        )

    def test_an_employee_cannot_decide_on_an_invoice(self, workspace):
        user, profile = employ(workspace)
        period = self._closed_march(workspace, profile, 600)
        invoice = HrInvoiceDocument.objects.create(
            workspace=workspace, profile=profile, period=period, claimed_minutes=720
        )
        assert client_for(user).post(
            url(workspace, f"invoices/{invoice.id}/reconcile/")
        ).status_code == 403

    def test_one_person_cannot_see_anothers_invoice(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        period = march_for(colleague)
        HrInvoiceDocument.objects.create(workspace=workspace, profile=colleague, period=period)
        assert client_for(user).get(url(workspace, "invoices/")).json() == []

    def test_the_reconciliation_verdict_cannot_be_sent_in(self, workspace):
        # Whether an invoice agrees with the month is worked out, never asserted.
        user, profile = employ(workspace)
        period = march_for(profile, minutes=600)
        response = client_for(user).post(
            url(workspace, "invoices/"),
            {
                "profile_id": str(profile.id),
                "period": str(period.id),
                "claimed_minutes": 600,
                "reconciliation_state": HrInvoiceDocument.ReconciliationState.MATCHED,
                "reconciled_minutes": 999,
            },
            format="json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["reconciliation_state"] == HrInvoiceDocument.ReconciliationState.PENDING
        assert body["reconciled_minutes"] is None
