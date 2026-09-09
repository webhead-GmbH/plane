# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""What is left of somebody's leave.

The entitlement says what was agreed; the absences say what has been taken. The
only question anybody asks before booking a week off is the difference, and it is
the one figure that has to be right — a balance read too high lets somebody take
leave they do not have, and nobody finds out until the year ends.

Held in minutes throughout. A day is not a fixed quantity for anyone working
uneven hours, so a balance kept in days stops meaning one thing the moment
contracted hours change.
"""

# Python imports
from datetime import date
from uuid import uuid4

# Third party imports
import pytest

# Module imports
from plane.hr.models import (
    HrAbsence,
    HrAbsenceType,
    HrContract,
    HrEmploymentProfile,
    HrHoliday,
    HrHolidayCalendar,
    HrLeaveEntitlement,
    HrPeriodDay,
    HrWorkSchedule,
)
from plane.hr.services.ledger import rebuild_period
from plane.hr.services.leave import standing, taken_between
from plane.tests.factories import UserFactory, WorkspaceFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

FULL = 462  # 7.7 hours, a day of the 38.5-hour week in force here.
YEAR_START = date(2026, 3, 1)
YEAR_END = date(2027, 2, 28)


@pytest.fixture
def workspace():
    return WorkspaceFactory(owner=UserFactory(username=uuid4().hex))


@pytest.fixture
def profile(workspace):
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=UserFactory(username=uuid4().hex),
        timezone="Europe/Vienna",
        hire_date=date(2024, 3, 1),
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
    return profile


def a_year_of(profile, minutes, carryover=0, start=YEAR_START, end=YEAR_END):
    return HrLeaveEntitlement.objects.create(
        workspace=profile.workspace,
        profile=profile,
        leave_year_start=start,
        leave_year_end=end,
        entitlement_minutes=minutes,
        carryover_minutes=carryover,
    )


def leave_type(workspace, consumes=True):
    return HrAbsenceType.objects.create(
        workspace=workspace,
        code=uuid4().hex[:8],
        name_de="Urlaub",
        credits_actual=True,
        consumes_leave_entitlement=consumes,
    )


def took(profile, absence_type, first, last, state=HrAbsence.State.APPROVED):
    from plane.hr.services.absences import resolve_total_minutes

    absence = HrAbsence.objects.create(
        workspace=profile.workspace,
        profile=profile,
        absence_type=absence_type,
        start_date=first,
        end_date=last,
        state=state,
    )
    absence.total_minutes = resolve_total_minutes(absence)
    absence.save(update_fields=["total_minutes", "updated_at"])
    return absence


class TestWhatIsLeft:
    def test_nothing_taken_leaves_all_of_it(self, profile):
        a_year_of(profile, 25 * FULL)
        assert standing(profile, date(2026, 6, 1))["remaining_minutes"] == 25 * FULL

    def test_a_week_off_comes_off_it(self, profile):
        a_year_of(profile, 25 * FULL)
        took(profile, leave_type(profile.workspace), date(2026, 6, 1), date(2026, 6, 5))

        result = standing(profile, date(2026, 6, 10))
        assert result["taken_minutes"] == 5 * FULL
        assert result["remaining_minutes"] == 20 * FULL

    def test_a_weekend_inside_the_week_costs_nothing(self, profile):
        a_year_of(profile, 25 * FULL)
        took(profile, leave_type(profile.workspace), date(2026, 6, 1), date(2026, 6, 7))

        assert standing(profile, date(2026, 6, 10))["taken_minutes"] == 5 * FULL

    def test_carried_over_leave_is_part_of_what_was_granted(self, profile):
        a_year_of(profile, 25 * FULL, carryover=3 * FULL)
        assert standing(profile, date(2026, 6, 1))["granted_minutes"] == 28 * FULL

    def test_an_absence_that_does_not_consume_leave_is_not_counted(self, profile):
        """Sickness is not a holiday, however the days look on a calendar."""
        a_year_of(profile, 25 * FULL)
        took(profile, leave_type(profile.workspace, consumes=False), date(2026, 6, 1), date(2026, 6, 5))

        assert standing(profile, date(2026, 6, 10))["taken_minutes"] == 0

    def test_leave_still_waiting_on_somebody_is_not_taken_yet(self, profile):
        """A refusal would otherwise put the balance back with nothing having happened."""
        a_year_of(profile, 25 * FULL)
        took(
            profile,
            leave_type(profile.workspace),
            date(2026, 6, 1),
            date(2026, 6, 5),
            state=HrAbsence.State.REQUESTED,
        )

        assert standing(profile, date(2026, 6, 10))["taken_minutes"] == 0

    def test_leave_taken_in_advance_shows_as_over(self, profile):
        """Signed, because showing nought left is a different and quieter wrong answer."""
        a_year_of(profile, 2 * FULL)
        took(profile, leave_type(profile.workspace), date(2026, 6, 1), date(2026, 6, 5))

        assert standing(profile, date(2026, 6, 10))["remaining_minutes"] == -3 * FULL

    def test_nobody_having_said_yet_is_not_the_same_as_none(self, profile):
        """A zero would read as the far more alarming statement that they have none."""
        assert standing(profile, date(2026, 6, 1)) is None


class TestTheBalanceAgreesWithTheMonth:
    """The same week off, counted twice, must not come to two different answers.

    The balance was worked out from the absence range against the schedule, and
    the month from the day-by-day ledger. The two disagree wherever the ledger
    knows something the range does not — a public holiday inside the week, which
    costs no leave, or sickness recorded over booked leave, which takes the day
    instead of it. In both cases the balance charged for a day the month did not,
    and the person was shown two figures for one week and no way to tell which was
    real.
    """

    def a_public_holiday_on(self, profile, day):
        calendar = HrHolidayCalendar.objects.create(
            workspace=profile.workspace, name="AT", country_code="AT", is_default=True
        )
        HrHoliday.objects.create(workspace=profile.workspace, calendar=calendar, date=day, name_de="Testfeiertag")
        return calendar

    def works_a_full_week(self, profile):
        """A contract, so the month records a target and holidays are worth something."""
        return HrContract.objects.create(
            workspace=profile.workspace,
            profile=profile,
            valid_from=date(2024, 1, 1),
            arrangement=HrContract.Arrangement.ONSITE_FULL_TIME,
            records_target_hours=True,
            records_leave_account=True,
            weekly_minutes=2310,
        )

    def test_a_public_holiday_inside_a_booked_week_costs_no_leave(self, profile):
        """Four days spent, not five. Charging the fifth is leave taken from nobody."""
        self.works_a_full_week(profile)
        self.a_public_holiday_on(profile, date(2026, 6, 3))
        a_year_of(profile, 25 * FULL)
        took(profile, leave_type(profile.workspace), date(2026, 6, 1), date(2026, 6, 5))

        assert standing(profile, date(2026, 6, 10))["taken_minutes"] == 4 * FULL

    def test_the_month_charges_exactly_what_the_balance_says(self, profile):
        self.works_a_full_week(profile)
        self.a_public_holiday_on(profile, date(2026, 6, 3))
        a_year_of(profile, 25 * FULL)
        took(profile, leave_type(profile.workspace), date(2026, 6, 1), date(2026, 6, 5))

        rebuild_period(profile, 2026, 6)
        charged_by_the_month = sum(
            day.leave_minutes for day in HrPeriodDay.objects.filter(profile_id=profile.id, work_date__month=6)
        )

        assert charged_by_the_month == standing(profile, date(2026, 6, 10))["taken_minutes"]

    def test_sickness_over_booked_leave_takes_the_day_instead_of_it(self, profile):
        """The ordinary case, and the one that costs somebody leave they kept."""
        self.works_a_full_week(profile)
        a_year_of(profile, 25 * FULL)
        holiday = leave_type(profile.workspace)
        holiday.precedence = 50
        holiday.save()
        sickness = HrAbsenceType.objects.create(
            workspace=profile.workspace,
            code=uuid4().hex[:8],
            name_de="Krankenstand",
            credits_actual=True,
            consumes_leave_entitlement=False,
            precedence=10,
        )
        took(profile, holiday, date(2026, 6, 1), date(2026, 6, 5))
        took(profile, sickness, date(2026, 6, 3), date(2026, 6, 3))

        assert standing(profile, date(2026, 6, 10))["taken_minutes"] == 4 * FULL

    def test_a_contract_that_says_no_leave_account_charges_nothing(self, profile):
        """Switching it off is a decision, and it is still respected."""
        contract = self.works_a_full_week(profile)
        contract.records_leave_account = False
        contract.save()
        a_year_of(profile, 25 * FULL)
        took(profile, leave_type(profile.workspace), date(2026, 6, 1), date(2026, 6, 5))

        assert standing(profile, date(2026, 6, 10))["taken_minutes"] == 0

    def test_no_contract_at_all_is_not_that_decision(self, profile):
        """Silence charges the leave: showing the whole year still free is the
        direction that lets somebody book leave they do not have."""
        a_year_of(profile, 25 * FULL)
        took(profile, leave_type(profile.workspace), date(2026, 6, 1), date(2026, 6, 5))

        assert standing(profile, date(2026, 6, 10))["taken_minutes"] == 5 * FULL


class TestTheYearItBelongsTo:
    def test_last_year_is_not_this_year(self, profile):
        a_year_of(profile, 25 * FULL, start=date(2025, 3, 1), end=date(2026, 2, 28))
        a_year_of(profile, 25 * FULL)
        took(profile, leave_type(profile.workspace), date(2025, 6, 2), date(2025, 6, 6))

        assert standing(profile, date(2026, 6, 1))["taken_minutes"] == 0

    def test_the_year_asked_about_is_the_one_the_day_falls_in(self, profile):
        a_year_of(profile, 10 * FULL, start=date(2025, 3, 1), end=date(2026, 2, 28))
        a_year_of(profile, 25 * FULL)

        assert standing(profile, date(2025, 9, 1))["granted_minutes"] == 10 * FULL
        assert standing(profile, date(2026, 9, 1))["granted_minutes"] == 25 * FULL

    def test_leave_lying_across_the_year_end_is_split_between_the_years(self, profile):
        """Counting it wholly in one year would overstate one and understate the other.

        The leave year runs from the hire anniversary, so this is not the rare
        new-year case it would be on a calendar basis — it is whichever week
        happens to straddle somebody's own anniversary.
        """
        took(
            profile,
            leave_type(profile.workspace),
            date(2027, 2, 24),  # Wednesday, in the old year
            date(2027, 3, 2),  # Tuesday, in the new one
        )

        old_year = taken_between(profile, YEAR_START, YEAR_END)
        new_year = taken_between(profile, date(2027, 3, 1), date(2028, 2, 29))

        assert old_year == 3 * FULL, "Wednesday to Friday"
        assert new_year == 2 * FULL, "Monday and Tuesday"
