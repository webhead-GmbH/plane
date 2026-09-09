# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Keeping open months up to date on a schedule.

The figures are also rebuilt whenever somebody looks at them, so this is not what
makes them correct. What it is for is the case where nobody looks: an entry that
disappeared in a month nobody has opened would otherwise go unnoticed until the
month was closed, which is exactly when it is least welcome.

Only months still in play are touched, and only the recent ones. Anything older
has either been closed or has nothing arriving in it.
"""

# Python imports
import logging

# Django imports
from django.conf import settings
from django.utils import timezone

# Third-party imports
from celery import shared_task

# Module imports
from plane.hr.conf import DEFAULT_REBUILD_MONTHS
from plane.hr.models import HrEmploymentProfile, HrPeriod
from plane.hr.services.ledger import rebuild_period
from plane.hr.utils.calendar import hr_local_date
from plane.utils.exception_logger import log_exception

logger = logging.getLogger("plane.worker")


def _recent_months(today, count):
    """This month and the ones just before it, newest first."""
    year, month = today.year, today.month
    for _ in range(count):
        yield year, month
        month -= 1
        if month == 0:
            year, month = year - 1, 12


@shared_task
def rebuild_open_periods():
    """Recompute every open month for everybody still employed."""
    months = int(getattr(settings, "HR_REBUILD_MONTHS", DEFAULT_REBUILD_MONTHS))
    rebuilt = 0

    for profile in HrEmploymentProfile.objects.filter(is_active=True).select_related("workspace"):
        zone = profile.timezone or getattr(profile.workspace, "timezone", "") or None
        today = hr_local_date(timezone.now(), zone)
        for year, month in _recent_months(today, months):
            try:
                if rebuild_period(profile, year, month) is not None:
                    rebuilt += 1
            except Exception as exc:  # noqa: BLE001 - one person must not stop the rest
                log_exception(exc)

    if rebuilt:
        logger.info("Rebuilt %s open month(s)", rebuilt)
    return rebuilt


@shared_task
def report_days_needing_review():
    """Count the days waiting on somebody to say what happened to them.

    Only counted and logged. Chasing people is a separate decision and belongs
    with the notification work, not here.
    """
    from plane.hr.models import HrPeriodDay

    waiting = HrPeriodDay.objects.filter(
        needs_review=True,
        period__state__in=(HrPeriod.State.OPEN, HrPeriod.State.REOPENED),
    ).count()
    if waiting:
        logger.info("%s day(s) are marked for review and block their month from closing", waiting)
    return waiting
