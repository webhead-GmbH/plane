# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""What somebody who invoices for their own hours should be invoicing.

The point of this is not filing invoices. It is that the module already knows how
many hours were agreed for the month, so it can say what the invoice ought to come
to and point out when it does not — which catches a mistake about money rather
than merely reporting a number, and settles most disagreements before an invoice
is written rather than after.

Rates here are internal: what an hour of somebody's time costs the company. They
are deliberately not the rates a customer is billed at, which live in the customer
system and stay there.
"""

# Python imports
from decimal import ROUND_HALF_UP, Decimal

# Module imports
from plane.hr.models import HrPeriod, HrRateCard
from plane.hr.services.refusal import Refused
from plane.hr.services.ledger import period_totals
from plane.hr.utils.resolve import effective

CENTS = Decimal("0.01")


def rate_for(profile, day):
    """The rate in force for somebody on a given day, or the workspace default."""
    personal = list(HrRateCard.objects.filter(profile_id=profile.id))
    found = effective(personal, day)
    if found is not None:
        return found
    defaults = list(HrRateCard.objects.filter(profile__isnull=True))
    return effective(defaults, day)


def _billable_minutes(period):
    """The hours an invoice should be based on.

    Taken from the closed figures once a month is closed, and from the live ones
    before that — the same rule as everywhere else, so a statement never disagrees
    with the month it came from.
    """
    if period.state == HrPeriod.State.LOCKED:
        return period.actual_minutes or 0
    return period_totals(period).get("actual_minutes") or 0


def statement_for(period):
    """What this month is worth, and what is still unsettled about it.

    Returned whether or not the month has been closed, because the useful moment
    for the person is before they write the invoice — but it says plainly which
    state the figures are in, since an open month can still move.
    """
    profile = period.profile
    rate = rate_for(profile, period.period_start)
    minutes = _billable_minutes(period)
    hours = (Decimal(minutes) / Decimal(60)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    expected = None
    if rate is not None:
        if rate.basis == HrRateCard.Basis.HOURLY and rate.hourly_rate is not None:
            expected = (Decimal(minutes) / Decimal(60) * rate.hourly_rate).quantize(CENTS, rounding=ROUND_HALF_UP)
        elif rate.monthly_amount is not None:
            expected = Decimal(rate.monthly_amount).quantize(CENTS, rounding=ROUND_HALF_UP)

    return {
        "period_id": str(period.id),
        "period_start": period.period_start,
        "period_end": period.period_end,
        "state": period.state,
        # Says out loud whether these figures can still move.
        "is_final": period.state == HrPeriod.State.LOCKED,
        "minutes": minutes,
        "hours": str(hours),
        "currency": rate.currency if rate else "",
        "rate_basis": rate.basis if rate else None,
        "hourly_rate": str(rate.hourly_rate) if rate and rate.hourly_rate is not None else None,
        "expected_amount": str(expected) if expected is not None else None,
        "has_rate": rate is not None,
    }


def reconcile(invoice):
    """Compare what an invoice claims against what the month says.

    Only against a closed month. Checking an invoice against figures that can
    still move would produce a variance that disappears on its own, which is worse
    than not checking at all — somebody would learn to ignore it.
    """
    period = invoice.period
    if period.state != HrPeriod.State.LOCKED:
        raise Refused("The month has not been closed yet, so there is nothing settled to check against.", conflict=True)

    invoice.reconciled_minutes = period.actual_minutes or 0
    if invoice.claimed_minutes is not None:
        invoice.variance_minutes = invoice.claimed_minutes - invoice.reconciled_minutes
    else:
        invoice.variance_minutes = None

    from plane.hr.models import HrInvoiceDocument

    if invoice.variance_minutes == 0:
        invoice.reconciliation_state = HrInvoiceDocument.ReconciliationState.MATCHED
    elif invoice.variance_minutes is None:
        invoice.reconciliation_state = HrInvoiceDocument.ReconciliationState.PENDING
    else:
        invoice.reconciliation_state = HrInvoiceDocument.ReconciliationState.DISPUTED
    return invoice
