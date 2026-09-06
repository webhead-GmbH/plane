# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Setting people up, and recording absence and non-project time."""

# Python imports
from datetime import date
from uuid import uuid4

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.app.permissions import ROLE
from plane.hr.models import (
    HrAbsence,
    HrAbsenceType,
    HrContract,
    HrEmploymentProfile,
    HrHolidayCalendar,
    HrPeriod,
    HrTimeEntry,
    HrWorkSchedule,
)
from plane.db.models import WorkspaceMember
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

FULL = 462


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
        hire_date=date(2024, 1, 1),
        is_hr_manager=is_hr_manager,
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


def url(workspace, path):
    return f"/api/hr/{path}"


class TestSetup:
    def test_it_creates_what_the_company_needs_to_start(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        response = client_for(manager).post(url(workspace, "setup/"))
        assert response.status_code == 200
        assert HrAbsenceType.objects.filter(workspace=workspace).count() == 6
        assert HrHolidayCalendar.objects.filter(workspace=workspace, is_default=True).exists()
        # The collective agreement week, not forty hours.
        default = HrWorkSchedule.objects.get(workspace=workspace, profile__isnull=True)
        assert default.monday_minutes == 462
        assert default.weekly_minutes == 462 * 5

    def test_sickness_outranks_leave(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        client_for(manager).post(url(workspace, "setup/"))
        sick = HrAbsenceType.objects.get(workspace=workspace, code="krankenstand")
        leave = HrAbsenceType.objects.get(workspace=workspace, code="urlaub")
        assert sick.precedence < leave.precedence

    def test_running_it_twice_changes_nothing(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        client = client_for(manager)
        client.post(url(workspace, "setup/"))
        response = client.post(url(workspace, "setup/"))
        assert response.json()["already_present"] is True
        assert HrAbsenceType.objects.filter(workspace=workspace).count() == 6

    def test_an_employee_cannot_run_it(self, workspace):
        user, _ = employ(workspace)
        assert client_for(user).post(url(workspace, "setup/")).status_code == 403


class TestPeople:
    def test_an_employee_sees_only_their_own_record(self, workspace):
        user, profile = employ(workspace)
        employ(workspace)
        response = client_for(user).get(url(workspace, "employees/"))
        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == [str(profile.id)]

    def test_a_manager_sees_everybody(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        employ(workspace)
        response = client_for(manager).get(url(workspace, "employees/"))
        assert len(response.json()) == 2

    def test_removing_somebody_marks_them_inactive_rather_than_deleting_them(self, workspace):
        # The months they worked still have to be readable.
        manager, _ = employ(workspace, is_hr_manager=True)
        _, leaver = employ(workspace)
        response = client_for(manager).delete(url(workspace, f"employees/{leaver.id}/"))
        assert response.status_code == 200
        leaver.refresh_from_db()
        assert leaver.is_active is False

    def test_an_employee_cannot_create_a_person(self, workspace):
        user, _ = employ(workspace)
        response = client_for(user).post(
            url(workspace, "employees/"), {"member": str(user.id)}, format="json"
        )
        assert response.status_code == 403


class TestContracts:
    def test_a_manager_can_record_terms(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        response = client_for(manager).post(
            url(workspace, f"employees/{profile.id}/contracts/"),
            {
                "valid_from": "2024-01-01",
                "arrangement": HrContract.Arrangement.ONSITE_FULL_TIME,
                "records_target_hours": True,
                "weekly_minutes": 2310,
            },
            format="json",
        )
        assert response.status_code == 201
        assert HrContract.objects.filter(profile=profile).count() == 1

    def test_overlapping_terms_are_refused(self, workspace):
        # Every day must have exactly one set of terms, or the target for that day
        # depends on which record happens to be found first.
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        client = client_for(manager)
        payload = {
            "valid_from": "2024-01-01",
            "arrangement": HrContract.Arrangement.ONSITE_FULL_TIME,
            "weekly_minutes": 2310,
        }
        assert client.post(
            url(workspace, f"employees/{profile.id}/contracts/"), payload, format="json"
        ).status_code == 201
        second = client.post(
            url(workspace, f"employees/{profile.id}/contracts/"),
            {**payload, "valid_from": "2025-01-01"},
            format="json",
        )
        assert second.status_code == 400
        assert "valid_from" in second.json()

    def test_terms_a_closed_month_relied_on_cannot_be_removed(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        contract = HrContract.objects.create(
            workspace=workspace,
            profile=profile,
            valid_from=date(2024, 1, 1),
            arrangement=HrContract.Arrangement.ONSITE_FULL_TIME,
        )
        HrPeriod.objects.create(
            workspace=workspace,
            profile=profile,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            state=HrPeriod.State.LOCKED,
            target_minutes=0,
            actual_minutes=0,
            balance_minutes=0,
        )
        response = client_for(manager).delete(
            url(workspace, f"employees/{profile.id}/contracts/{contract.id}/")
        )
        assert response.status_code == 409

    def test_an_employee_cannot_read_a_colleagues_terms(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        response = client_for(user).get(url(workspace, f"employees/{colleague.id}/contracts/"))
        assert response.status_code == 404


class TestSharedReferenceData:
    def test_everybody_can_read_the_holidays(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        client_for(manager).post(url(workspace, "setup/"))
        user, _ = employ(workspace)
        assert client_for(user).get(url(workspace, "holidays/")).status_code == 200
        assert client_for(user).get(url(workspace, "holiday-calendars/")).status_code == 200

    def test_everybody_can_read_the_absence_types(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        client_for(manager).post(url(workspace, "setup/"))
        user, _ = employ(workspace)
        response = client_for(user).get(url(workspace, "absence-types/"))
        assert response.status_code == 200
        assert len(response.json()) == 6

    def test_only_a_manager_can_change_them(self, workspace):
        user, _ = employ(workspace)
        response = client_for(user).post(
            url(workspace, "absence-types/"),
            {"code": "made-up", "name_de": "Erfunden"},
            format="json",
        )
        assert response.status_code == 403

    def test_only_a_manager_can_read_the_schedules(self, workspace):
        user, _ = employ(workspace)
        assert client_for(user).get(url(workspace, "schedules/")).status_code == 403


class TestAbsences:
    @pytest.fixture
    def leave_type(self, workspace):
        return HrAbsenceType.objects.create(
            workspace=workspace,
            code="urlaub",
            name_de="Urlaub",
            credits_actual=True,
            consumes_leave_entitlement=True,
        )

    def test_asking_for_leave_creates_a_request(self, workspace, leave_type):
        user, profile = employ(workspace)
        response = client_for(user).post(
            url(workspace, "absences/"),
            {
                "profile_id": str(profile.id),
                "absence_type": str(leave_type.id),
                "start_date": "2026-03-02",
                "end_date": "2026-03-06",
            },
            format="json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["state"] == HrAbsence.State.REQUESTED
        # Five working days, resolved once against the schedule in force.
        assert body["total_minutes"] == FULL * 5

    def test_a_manager_recording_an_agreed_absence_does_not_request_it(self, workspace, leave_type):
        manager, profile = employ(workspace, is_hr_manager=True)
        response = client_for(manager).post(
            url(workspace, "absences/"),
            {
                "profile_id": str(profile.id),
                "absence_type": str(leave_type.id),
                "start_date": "2026-03-02",
                "end_date": "2026-03-02",
            },
            format="json",
        )
        assert response.json()["state"] == HrAbsence.State.APPROVED

    def test_a_weekend_inside_a_range_costs_nothing(self, workspace, leave_type):
        manager, profile = employ(workspace, is_hr_manager=True)
        response = client_for(manager).post(
            url(workspace, "absences/"),
            {
                "profile_id": str(profile.id),
                "absence_type": str(leave_type.id),
                "start_date": "2026-03-02",
                "end_date": "2026-03-08",  # Monday to Sunday
            },
            format="json",
        )
        assert response.json()["total_minutes"] == FULL * 5

    def test_deciding_on_your_own_absence_is_refused(self, workspace, leave_type):
        manager, profile = employ(workspace, is_hr_manager=True)
        absence = HrAbsence.objects.create(
            workspace=workspace,
            profile=profile,
            absence_type=leave_type,
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
            state=HrAbsence.State.REQUESTED,
        )
        response = client_for(manager).post(url(workspace, f"absences/{absence.id}/approve/"))
        assert response.status_code == 403

    def test_a_manager_approves_somebody_elses(self, workspace, leave_type):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        absence = HrAbsence.objects.create(
            workspace=workspace,
            profile=profile,
            absence_type=leave_type,
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
            state=HrAbsence.State.REQUESTED,
        )
        response = client_for(manager).post(url(workspace, f"absences/{absence.id}/approve/"))
        assert response.status_code == 200
        assert response.json()["state"] == HrAbsence.State.APPROVED
        assert response.json()["total_minutes"] == FULL

    def test_refusing_requires_saying_why(self, workspace, leave_type):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        absence = HrAbsence.objects.create(
            workspace=workspace,
            profile=profile,
            absence_type=leave_type,
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
            state=HrAbsence.State.REQUESTED,
        )
        client = client_for(manager)
        assert client.post(url(workspace, f"absences/{absence.id}/reject/")).status_code == 400
        ok = client.post(
            url(workspace, f"absences/{absence.id}/reject/"),
            {"reason": "The whole team is away that week."},
            format="json",
        )
        assert ok.status_code == 200

    def test_the_team_calendar_shows_that_somebody_is_away_but_not_why(self, workspace, leave_type):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        HrAbsence.objects.create(
            workspace=workspace,
            profile=profile,
            absence_type=leave_type,
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 6),
            state=HrAbsence.State.APPROVED,
            reason="A private matter.",
        )
        user, _ = employ(workspace)
        response = client_for(user).get(url(workspace, "absences/calendar/"))
        assert response.status_code == 200
        row = response.json()[0]
        assert row["start_date"] == "2026-03-02"
        assert "member_display_name" in row
        # A colleague has no business with the type or the reason.
        assert "absence_type" not in row
        assert "reason" not in row

    def test_an_absence_a_closed_month_counted_cannot_be_changed(self, workspace, leave_type):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        period = HrPeriod.objects.create(
            workspace=workspace,
            profile=profile,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            state=HrPeriod.State.LOCKED,
            target_minutes=0,
            actual_minutes=0,
            balance_minutes=0,
        )
        absence = HrAbsence.objects.create(
            workspace=workspace,
            profile=profile,
            absence_type=leave_type,
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
            state=HrAbsence.State.APPROVED,
            locked_period=period,
        )
        response = client_for(manager).patch(
            url(workspace, f"absences/{absence.id}/"), {"end_date": "2026-03-04"}, format="json"
        )
        assert response.status_code == 409


class TestTimeEntries:
    def test_somebody_can_record_their_own_meeting_time(self, workspace):
        user, profile = employ(workspace)
        response = client_for(user).post(
            url(workspace, "time-entries/"),
            {
                "profile_id": str(profile.id),
                "entry_date": "2026-03-02",
                "minutes": 90,
                "category": HrTimeEntry.Category.MEETING,
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["source"] == HrTimeEntry.Source.MANUAL

    def test_an_entry_of_no_time_is_refused(self, workspace):
        user, profile = employ(workspace)
        response = client_for(user).post(
            url(workspace, "time-entries/"),
            {"profile_id": str(profile.id), "entry_date": "2026-03-02", "minutes": 0},
            format="json",
        )
        assert response.status_code == 400

    def test_more_than_a_day_in_a_day_is_refused(self, workspace):
        user, profile = employ(workspace)
        response = client_for(user).post(
            url(workspace, "time-entries/"),
            {"profile_id": str(profile.id), "entry_date": "2026-03-02", "minutes": 2000},
            format="json",
        )
        assert response.status_code == 400

    def test_one_person_cannot_record_time_against_another(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        response = client_for(user).post(
            url(workspace, "time-entries/"),
            {"profile_id": str(colleague.id), "entry_date": "2026-03-02", "minutes": 60},
            format="json",
        )
        assert response.status_code == 404

    def test_one_person_cannot_see_anothers_entries(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        HrTimeEntry.objects.create(
            workspace=workspace, profile=colleague, entry_date=date(2026, 3, 2), minutes=60
        )
        response = client_for(user).get(url(workspace, "time-entries/"))
        assert response.json() == []


class TestCandidates:
    """Who can still be given an employment record."""

    def test_it_offers_somebody_not_yet_employed(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        newcomer = new_user()
        WorkspaceMemberFactory(workspace=workspace, member=newcomer, role=ROLE.MEMBER.value)

        response = client_for(manager).get(url(workspace, "candidates/"))
        assert response.status_code == 200
        assert str(newcomer.id) in [row["id"] for row in response.json()]

    def test_it_leaves_out_people_who_already_have_a_record(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        colleague, _ = employ(workspace)

        offered = [row["id"] for row in client_for(manager).get(url(workspace, "candidates/")).json()]
        assert str(colleague.id) not in offered
        assert str(manager.id) not in offered

    def test_it_reaches_across_workspaces(self, workspace):
        # Employment is with the company. Somebody working only in another
        # workspace is still a colleague who needs a month.
        manager, _ = employ(workspace, is_hr_manager=True)
        elsewhere = WorkspaceFactory(owner=new_user())
        stranger = new_user()
        WorkspaceMemberFactory(workspace=elsewhere, member=stranger, role=ROLE.MEMBER.value)

        offered = [row["id"] for row in client_for(manager).get(url(workspace, "candidates/")).json()]
        assert str(stranger.id) in offered

    def test_it_leaves_out_bots(self, workspace):
        # They hold membership so they can act through the API; nobody pays one.
        manager, _ = employ(workspace, is_hr_manager=True)
        bot = new_user()
        bot.is_bot = True
        bot.save()
        WorkspaceMemberFactory(workspace=workspace, member=bot, role=ROLE.MEMBER.value)

        offered = [row["id"] for row in client_for(manager).get(url(workspace, "candidates/")).json()]
        assert str(bot.id) not in offered

    def test_it_leaves_out_somebody_removed_from_every_workspace(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        gone = new_user()
        membership = WorkspaceMemberFactory(workspace=workspace, member=gone, role=ROLE.MEMBER.value)
        membership.is_active = False
        membership.save()

        offered = [row["id"] for row in client_for(manager).get(url(workspace, "candidates/")).json()]
        assert str(gone.id) not in offered

    def test_an_employee_cannot_see_the_list(self, workspace):
        user, _ = employ(workspace)
        assert client_for(user).get(url(workspace, "candidates/")).status_code == 403


class TestTimeEntryScoping:
    """Whose hours come back when a day is asked for.

    A manager may see everybody, which is right for a report and wrong for a
    screen showing one person's day: unscoped, it would list — and offer to
    delete — a colleague's hours under somebody else's name.
    """

    def _hours(self, profile, day, minutes, note):
        return HrTimeEntry.objects.create(
            workspace=profile.workspace,
            profile=profile,
            entry_date=day,
            minutes=minutes,
            note=note,
        )

    def test_asking_for_one_person_returns_only_theirs(self, workspace):
        manager, manager_profile = employ(workspace, is_hr_manager=True)
        _, colleague = employ(workspace)
        day = date(2026, 8, 20)
        self._hours(manager_profile, day, 60, "mine")
        self._hours(colleague, day, 120, "theirs")

        response = client_for(manager).get(
            url(workspace, f"time-entries/?from={day}&to={day}&profile_id={manager_profile.id}")
        )
        assert response.status_code == 200
        assert [row["note"] for row in response.json()] == ["mine"]

    def test_a_manager_asking_for_nobody_in_particular_sees_everybody(self, workspace):
        # The wider answer stays available; it is simply not what a day view asks.
        manager, manager_profile = employ(workspace, is_hr_manager=True)
        _, colleague = employ(workspace)
        day = date(2026, 8, 20)
        self._hours(manager_profile, day, 60, "mine")
        self._hours(colleague, day, 120, "theirs")

        rows = client_for(manager).get(url(workspace, f"time-entries/?from={day}&to={day}")).json()
        assert sorted(row["note"] for row in rows) == ["mine", "theirs"]

    def test_one_person_cannot_ask_for_a_colleagues_day(self, workspace):
        user, _ = employ(workspace)
        _, colleague = employ(workspace)
        day = date(2026, 8, 20)
        self._hours(colleague, day, 120, "theirs")

        rows = client_for(user).get(
            url(workspace, f"time-entries/?from={day}&to={day}&profile_id={colleague.id}")
        ).json()
        assert rows == []

class TestCrmStaffMapping:
    """Which CRM staff account somebody's hours are pushed to.

    The sync prefers the id set on the workspace membership and falls back to
    matching email addresses. That fallback is a guess, and when it misses, the
    hours never become a CRM timer and nothing but a log line says so — which is
    why the screen has to be able to both show and set the id.
    """

    def test_somebody_with_no_id_set_is_shown_as_matched_by_email(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        response = client_for(manager).get(url(workspace, f"employees/{profile.id}/"))
        assert response.status_code == 200
        assert response.data["crm_staff_id"] is None
        assert response.data["crm_link"] == "email"

    def test_setting_an_id_records_it_and_says_it_was_set(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        response = client_for(manager).patch(
            url(workspace, f"employees/{profile.id}/"), {"crm_staff_id": 42}, format="json"
        )
        assert response.status_code == 200
        assert response.data["crm_staff_id"] == 42
        assert response.data["crm_link"] == "set"
        assert WorkspaceMember.objects.get(workspace=workspace, member=profile.member).crm_staff_id == 42

    def test_clearing_it_puts_them_back_on_the_email_match(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        client = client_for(manager)
        client.patch(url(workspace, f"employees/{profile.id}/"), {"crm_staff_id": 7}, format="json")
        response = client.patch(
            url(workspace, f"employees/{profile.id}/"), {"crm_staff_id": ""}, format="json"
        )
        assert response.status_code == 200
        assert response.data["crm_staff_id"] is None
        assert response.data["crm_link"] == "email"

    def test_the_id_reaches_every_workspace_the_person_is_in(self, workspace):
        """One person is one employee, so one CRM account — not one per workspace.

        Setting it in one workspace and not another would leave the sync guessing
        wherever it was missed, which is the failure this exists to remove.
        """
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        elsewhere = WorkspaceFactory(owner=new_user())
        WorkspaceMemberFactory(workspace=elsewhere, member=profile.member, role=ROLE.MEMBER.value)

        client_for(manager).patch(
            url(workspace, f"employees/{profile.id}/"), {"crm_staff_id": 9}, format="json"
        )
        assert WorkspaceMember.objects.get(workspace=elsewhere, member=profile.member).crm_staff_id == 9

    def test_something_that_is_not_a_staff_id_is_refused(self, workspace):
        manager, _ = employ(workspace, is_hr_manager=True)
        _, profile = employ(workspace)
        for bad in ("abc", 0, -3):
            response = client_for(manager).patch(
                url(workspace, f"employees/{profile.id}/"), {"crm_staff_id": bad}, format="json"
            )
            assert response.status_code == 400, bad

    def test_an_employee_cannot_set_their_own(self, workspace):
        user, profile = employ(workspace)
        response = client_for(user).patch(
            url(workspace, f"employees/{profile.id}/"), {"crm_staff_id": 5}, format="json"
        )
        assert response.status_code == 403
        assert WorkspaceMember.objects.get(workspace=workspace, member=user).crm_staff_id is None
