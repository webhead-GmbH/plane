# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A month that is still running reports two figures, not one.

What the contract owes for the whole month and how somebody stands so far are
different questions. Answering the second with the first charges every day that
has not arrived as a shortfall — on the first of the month, the whole month — and
the number people were meant to check daily becomes one they learn to ignore.

The clock is frozen in every test here. A test that reads the real date passes in
August and fails in September, which is the same class of bug it is testing for.
"""

# Python imports
from datetime import date
from uuid import uuid4

# Third-party imports
import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import (
    HrContract,
    HrEmploymentProfile,
    HrPeriod,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.hr.services import closing
from plane.hr.services.ledger import rebuild_period
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

FULL = 462  # 38.5 hours over five days


@pytest.fixture(autouse=True, scope="module")
def _load_the_urlconf():
    """Resolve the root URLconf before any test freezes the clock.

    Django loads it on the first request, and one of the view modules it reaches
    defines a class deriving from ``datetime.date`` at import time. Import that
    while the clock is frozen and the base class is freezegun's stand-in, which
    fails with a metaclass conflict that has nothing to do with the test.
    """
    from django.urls import get_resolver

    get_resolver().url_patterns


def new_user():
    return UserFactory(username=uuid4().hex)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def workspace():
    owner = new_user()
    workspace = WorkspaceFactory(owner=owner)
    WorkspaceMemberFactory(workspace=workspace, member=owner, role=ROLE.ADMIN.value)
    return workspace


def employ(workspace, is_hr_manager=False):
    user = new_user()
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ROLE.MEMBER.value)
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=user,
        timezone="Europe/Vienna",
        hire_date=date(2020, 1, 1),
        is_hr_manager=is_hr_manager,
    )
    HrContract.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2020, 1, 1),
        arrangement=HrContract.Arrangement.ONSITE_FULL_TIME,
        records_target_hours=True,
        weekly_minutes=FULL * 5,
    )
    HrWorkSchedule.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2020, 1, 1),
        monday_minutes=FULL,
        tuesday_minutes=FULL,
        wednesday_minutes=FULL,
        thursday_minutes=FULL,
        friday_minutes=FULL,
    )
    return user, profile


def worked(profile, day, minutes):
    HrTimeEntry.objects.create(
        workspace=profile.workspace, profile=profile, entry_date=day, minutes=minutes
    )


class TestFiguresSoFar:
    def test_a_running_month_reports_where_the_person_stands_today(self, workspace):
        # March 2026 has 22 weekdays. By the 4th, three of them have been worked.
        user, profile = employ(workspace)
        for day in (date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4)):
            worked(profile, day, FULL)

        with freeze_time("2026-03-04 15:00:00+01:00"):
            body = client_for(user).get("/api/hr/me/?year=2026&month=3").json()["period"]

        assert body["target_minutes"] == FULL * 22, "the contract still owes the whole month"
        assert body["to_date"]["counted_through"] == "2026-03-04"
        assert body["to_date"]["target_minutes"] == FULL * 3
        assert body["to_date"]["actual_minutes"] == FULL * 3
        assert body["to_date"]["balance_minutes"] == 0, "level, not nineteen days behind"

    def test_the_first_of_the_month_counts_the_first_of_the_month(self, workspace):
        # Cutting at yesterday lands on the previous month, matches no rows, and
        # every figure comes back empty under a caption naming the wrong month.
        user, profile = employ(workspace)

        with freeze_time("2026-03-01 09:00:00+01:00"):
            body = client_for(user).get("/api/hr/me/?year=2026&month=3").json()["period"]

        to_date = body["to_date"]
        assert to_date["counted_through"] == "2026-03-01"
        assert to_date["target_minutes"] == 0, "the first is a Sunday, so nothing is owed yet"
        assert to_date["balance_minutes"] == 0
        assert to_date["actual_minutes"] is not None, "an uncounted month is zero, not unknown"

    def test_hours_logged_today_are_in_the_figure_today(self, workspace):
        # The screen exists to show somebody the hours they just logged.
        user, profile = employ(workspace)
        worked(profile, date(2026, 3, 4), 300)

        with freeze_time("2026-03-04 17:30:00+01:00"):
            body = client_for(user).get("/api/hr/me/?year=2026&month=3").json()["period"]

        assert body["to_date"]["actual_minutes"] == 300

    def test_a_month_that_has_ended_is_its_own_answer(self, workspace):
        user, profile = employ(workspace)

        with freeze_time("2026-04-02 09:00:00+01:00"):
            body = client_for(user).get("/api/hr/me/?year=2026&month=3").json()["period"]

        assert "to_date" not in body, "nothing is still to come, so there is one figure"

    def test_the_last_day_of_the_month_is_already_the_whole_month(self, workspace):
        # Otherwise the balance moves by a whole working day at midnight.
        user, profile = employ(workspace)

        with freeze_time("2026-03-31 23:59:00+02:00"):
            body = client_for(user).get("/api/hr/me/?year=2026&month=3").json()["period"]

        assert "to_date" not in body

    def test_a_closed_month_never_carries_a_running_figure(self, workspace):
        user, profile = employ(workspace)
        period = rebuild_period(profile, 2026, 3)
        period.state = HrPeriod.State.LOCKED
        period.target_minutes = 0
        period.actual_minutes = 0
        period.balance_minutes = 0
        period.save()

        with freeze_time("2026-03-04 15:00:00+01:00"):
            body = client_for(user).get("/api/hr/me/?year=2026&month=3").json()["period"]

        assert "to_date" not in body

    def test_the_manager_sees_each_person_measured_in_their_own_month(self, workspace):
        manager_user, _ = employ(workspace, is_hr_manager=True)
        employ(workspace)

        with freeze_time("2026-03-04 15:00:00+01:00"):
            body = client_for(manager_user).get("/api/hr/overview/?year=2026&month=3").json()

        assert len(body["rows"]) == 2
        for row in body["rows"]:
            assert row["to_date"]["counted_through"] == "2026-03-04"
            assert row["target_minutes"] == FULL * 22
            assert row["to_date"]["target_minutes"] == FULL * 3


class TestFinishingAMonthEarly:
    """Closing a month before it has happened freezes a shortfall nobody incurred.

    Worse than the same error on a screen, because the frozen figure is carried
    into every later month by the opening balance and can only be undone by
    reopening a month that has already been agreed.
    """

    def test_a_month_still_running_cannot_be_handed_in(self, workspace):
        user, profile = employ(workspace)
        period = rebuild_period(profile, 2026, 3)

        with freeze_time("2026-03-04 15:00:00+01:00"):
            with pytest.raises(closing.TransitionRefused):
                closing.submit(period, user)

    def test_the_refusal_says_when_it_becomes_possible(self, workspace):
        user, profile = employ(workspace)
        period = rebuild_period(profile, 2026, 3)

        with freeze_time("2026-03-04 15:00:00+01:00"):
            with pytest.raises(closing.TransitionRefused) as refused:
                closing.submit(period, user)

        assert "2026-04-01" in str(refused.value)

    def test_the_last_day_is_still_too_early(self, workspace):
        # The day is not over, so neither is the month.
        user, profile = employ(workspace)
        period = rebuild_period(profile, 2026, 3)

        with freeze_time("2026-03-31 22:00:00+02:00"):
            with pytest.raises(closing.TransitionRefused):
                closing.submit(period, user)

    def test_the_day_after_it_ends_is_soon_enough(self, workspace):
        user, profile = employ(workspace)
        period = rebuild_period(profile, 2026, 3)

        with freeze_time("2026-04-01 08:00:00+02:00"):
            closing.submit(period, user)

        period.refresh_from_db()
        assert period.state == HrPeriod.State.SUBMITTED

    def test_closing_checks_again_rather_than_trusting_the_earlier_step(self, workspace):
        # Reaching APPROVED does not license freezing a month that is running.
        manager_user, _ = employ(workspace, is_hr_manager=True)
        user, profile = employ(workspace)
        period = rebuild_period(profile, 2026, 3)
        HrPeriod.objects.filter(pk=period.pk).update(state=HrPeriod.State.APPROVED)
        period.refresh_from_db()

        with freeze_time("2026-03-15 12:00:00+01:00"):
            with pytest.raises(closing.TransitionRefused):
                closing.lock(period, manager_user)

    def test_the_boundary_is_the_persons_own_date_not_the_servers(self, workspace):
        # 1 April in Vienna is still 31 March in UTC. The month belongs to the
        # person, so it is their midnight that ends it.
        user, profile = employ(workspace)
        period = rebuild_period(profile, 2026, 3)

        with freeze_time("2026-03-31 23:30:00+00:00"):  # 01:30 on 1 April in Vienna
            closing.submit(period, user)

        period.refresh_from_db()
        assert period.state == HrPeriod.State.SUBMITTED
