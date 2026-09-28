# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Timers started and stopped in the CRM, arriving in Plane."""

# Python imports
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock
from uuid import uuid4

# Third-party imports
import pytest
from rest_framework.test import APIClient

# Module imports
from plane.db.models import (
    CrmIntegration,
    CrmTaskLink,
    CrmTimerLink,
    Issue,
    IssueWorkLog,
    State,
)
from plane.tests.factories import (
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    WorkspaceFactory,
    WorkspaceMemberFactory,
)
from plane.utils.crm_timer_inbound import (
    TIMER_STARTED,
    TIMER_STOPPED,
    apply_crm_timer_event,
    plane_user_for_crm_staff,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

CRM_TASK_ID = 501
STAFF_ID = 7
SECRET = "s" * 64
NINE = datetime(2026, 9, 28, 9, 0, tzinfo=dt_timezone.utc)


def ts(moment):
    return int(moment.timestamp())


@pytest.fixture
def setup():
    """A workspace with its CRM integration, one mirrored work item and its assignee."""
    owner = UserFactory(username=uuid4().hex)
    workspace = WorkspaceFactory(owner=owner)
    person = UserFactory(username=uuid4().hex, email="person@example.com")
    WorkspaceMemberFactory(workspace=workspace, member=person, role=15)
    project = ProjectFactory(workspace=workspace, created_by=owner, updated_by=owner)
    ProjectMemberFactory(project=project, member=person, role=15)
    state = State.objects.create(name="Doing", project=project, workspace=workspace, group="started")
    issue = Issue.objects.create(project=project, workspace=workspace, name="Build it", state=state)
    CrmTaskLink.objects.create(workspace=workspace, issue=issue, crm_task_id=CRM_TASK_ID, crm_project_id=1)
    integration = CrmIntegration(workspace=workspace, crm_api_url="https://crm.example.com")
    integration.set_api_key("key")
    integration.save()
    return {"workspace": workspace, "person": person, "project": project, "issue": issue, "integration": integration}


def crm_timer(timer_id=900, start=NINE, end=None, note=None, staff_email="person@example.com", staff_id=STAFF_ID):
    return {
        "id": timer_id,
        "task_id": CRM_TASK_ID,
        "staff_id": staff_id,
        "staff_email": staff_email,
        "start_time": ts(start),
        "end_time": ts(end) if end else None,
        "note": note,
    }


def running_timers(user):
    return IssueWorkLog.objects.filter(logged_by=user, duration__isnull=True)


class TestTimerStartedInCrm:
    def test_starts_a_plane_timer_linked_to_the_crm_timer(self, setup):
        result = apply_crm_timer_event(setup["integration"], TIMER_STARTED, crm_timer())

        assert result == "started"
        worklog = running_timers(setup["person"]).get()
        assert worklog.issue_id == setup["issue"].id
        assert worklog.started_at == NINE
        assert CrmTimerLink.objects.get(worklog=worklog).crm_timer_id == 900

    def test_is_not_sent_back_to_the_crm(self, setup, django_capture_on_commit_callbacks):
        with mock.patch("plane.bgtasks.crm_sync_task.sync_worklog_to_crm.delay") as mirror:
            with django_capture_on_commit_callbacks(execute=True):
                apply_crm_timer_event(setup["integration"], TIMER_STARTED, crm_timer())

        mirror.assert_not_called()

    def test_a_repeated_delivery_changes_nothing(self, setup):
        apply_crm_timer_event(setup["integration"], TIMER_STARTED, crm_timer())
        result = apply_crm_timer_event(setup["integration"], TIMER_STARTED, crm_timer())

        assert result == "ignored: already running in Plane"
        assert IssueWorkLog.objects.filter(logged_by=setup["person"]).count() == 1

    def test_stops_the_other_timer_the_person_had_running(self, setup, django_capture_on_commit_callbacks):
        earlier = IssueWorkLog.objects.create(
            workspace=setup["workspace"],
            project=setup["project"],
            issue=setup["issue"],
            logged_by=setup["person"],
            started_at=NINE - timedelta(hours=1),
            logged_at=NINE - timedelta(hours=1),
        )

        with mock.patch("plane.bgtasks.crm_sync_task.sync_worklog_to_crm.delay") as mirror:
            with django_capture_on_commit_callbacks(execute=True):
                apply_crm_timer_event(setup["integration"], TIMER_STARTED, crm_timer())

        earlier.refresh_from_db()
        assert earlier.duration == 3600
        # the one Plane stopped on its own account still has to reach the CRM
        mirror.assert_called_once_with(str(earlier.id))

    def test_ignores_a_task_plane_does_not_mirror(self, setup):
        timer = {**crm_timer(), "task_id": CRM_TASK_ID + 1}

        assert apply_crm_timer_event(setup["integration"], TIMER_STARTED, timer) == (
            "ignored: task not linked to a work item"
        )
        assert not running_timers(setup["person"]).exists()

    def test_ignores_staff_with_no_plane_account(self, setup):
        timer = crm_timer(staff_email="stranger@example.com", staff_id=99)

        assert apply_crm_timer_event(setup["integration"], TIMER_STARTED, timer).startswith("ignored: no Plane member")

    def test_ignores_someone_outside_the_project(self, setup):
        outsider = UserFactory(username=uuid4().hex, email="outsider@example.com")
        WorkspaceMemberFactory(workspace=setup["workspace"], member=outsider, role=15)

        result = apply_crm_timer_event(setup["integration"], TIMER_STARTED, crm_timer(staff_email=outsider.email))

        assert result == "ignored: not a member of the work item's project"


class TestTimerStoppedInCrm:
    def test_stops_the_plane_timer_at_the_crm_end_time(self, setup):
        apply_crm_timer_event(setup["integration"], TIMER_STARTED, crm_timer())

        result = apply_crm_timer_event(
            setup["integration"],
            TIMER_STOPPED,
            crm_timer(end=NINE + timedelta(minutes=45), note="Reviewed the draft"),
        )

        assert result == "stopped"
        worklog = IssueWorkLog.objects.get(logged_by=setup["person"])
        assert worklog.duration == 45 * 60
        assert worklog.description == "Reviewed the draft"

    def test_stops_a_timer_that_was_started_in_plane(self, setup):
        worklog = IssueWorkLog.objects.create(
            workspace=setup["workspace"],
            project=setup["project"],
            issue=setup["issue"],
            logged_by=setup["person"],
            started_at=NINE,
            logged_at=NINE,
        )
        CrmTimerLink.objects.create(workspace=setup["workspace"], worklog=worklog, crm_timer_id=900)

        result = apply_crm_timer_event(setup["integration"], TIMER_STOPPED, crm_timer(end=NINE + timedelta(hours=2)))

        assert result == "stopped"
        worklog.refresh_from_db()
        assert worklog.duration == 2 * 3600

    def test_counts_the_same_seconds_as_the_crm(self, setup):
        # Plane's own start has a fraction of a second; the CRM stores the whole second.
        worklog = IssueWorkLog.objects.create(
            workspace=setup["workspace"],
            project=setup["project"],
            issue=setup["issue"],
            logged_by=setup["person"],
            started_at=NINE + timedelta(milliseconds=700),
            logged_at=NINE,
        )
        CrmTimerLink.objects.create(workspace=setup["workspace"], worklog=worklog, crm_timer_id=900)

        apply_crm_timer_event(setup["integration"], TIMER_STOPPED, crm_timer(end=NINE + timedelta(seconds=144)))

        worklog.refresh_from_db()
        assert worklog.duration == 144

    def test_a_timer_already_stopped_stays_as_it_is(self, setup):
        apply_crm_timer_event(setup["integration"], TIMER_STARTED, crm_timer())
        apply_crm_timer_event(setup["integration"], TIMER_STOPPED, crm_timer(end=NINE + timedelta(minutes=10)))

        result = apply_crm_timer_event(setup["integration"], TIMER_STOPPED, crm_timer(end=NINE + timedelta(hours=5)))

        assert result == "ignored: already stopped in Plane"
        assert IssueWorkLog.objects.get(logged_by=setup["person"]).duration == 600

    def test_a_timer_whose_start_never_arrived_is_recorded_whole(self, setup):
        result = apply_crm_timer_event(setup["integration"], TIMER_STOPPED, crm_timer(end=NINE + timedelta(minutes=30)))

        assert result == "recorded"
        worklog = IssueWorkLog.objects.get(logged_by=setup["person"])
        assert worklog.duration == 30 * 60
        assert CrmTimerLink.objects.get(worklog=worklog).crm_timer_id == 900


class TestStaffMatching:
    def test_an_explicit_crm_staff_id_wins_over_the_email(self, setup):
        other = UserFactory(username=uuid4().hex, email="other@example.com")
        WorkspaceMemberFactory(workspace=setup["workspace"], member=other, role=15, crm_staff_id=STAFF_ID)

        assert plane_user_for_crm_staff(setup["workspace"].id, STAFF_ID, "person@example.com") == other

    def test_a_member_mapped_to_another_crm_account_is_not_matched_by_email(self, setup):
        member = setup["person"].member_workspace.get(workspace=setup["workspace"])
        member.crm_staff_id = STAFF_ID + 1
        member.save(update_fields=["crm_staff_id"])

        assert plane_user_for_crm_staff(setup["workspace"].id, STAFF_ID, "person@example.com") is None


class TestTimerWebhook:
    def post(self, setup, payload, secret=SECRET):
        body = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return APIClient().post(
            f"/api/workspaces/{setup['workspace'].slug}/crm-integration/timer-webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_PLANE_API_SIGNATURE=signature,
        )

    def with_secret(self, setup):
        from plane.license.utils.encryption import encrypt_data

        setup["integration"].timer_webhook_secret_encrypted = encrypt_data(SECRET)
        setup["integration"].save(update_fields=["timer_webhook_secret_encrypted"])

    def test_a_signed_event_starts_the_timer(self, setup):
        self.with_secret(setup)

        response = self.post(setup, {"event": TIMER_STARTED, "sent_at": int(time.time()), "timer": crm_timer()})

        assert response.status_code == 200
        assert response.json() == {"result": "started"}
        assert running_timers(setup["person"]).exists()

    def test_a_wrong_signature_is_refused(self, setup):
        self.with_secret(setup)

        response = self.post(
            setup, {"event": TIMER_STARTED, "sent_at": int(time.time()), "timer": crm_timer()}, secret="x" * 64
        )

        assert response.status_code == 401
        assert not running_timers(setup["person"]).exists()

    def test_an_old_event_is_refused(self, setup):
        self.with_secret(setup)

        response = self.post(setup, {"event": TIMER_STARTED, "sent_at": int(time.time()) - 3600, "timer": crm_timer()})

        assert response.status_code == 400

    def test_nothing_is_accepted_before_a_webhook_is_registered(self, setup):
        response = self.post(setup, {"event": TIMER_STARTED, "sent_at": int(time.time()), "timer": crm_timer()})

        assert response.status_code == 404


class TestReconcilingStops:
    def test_a_crm_timer_stopped_without_an_event_stops_the_plane_timer(self, setup):
        from plane.bgtasks.crm_sync_task import reconcile_crm_timer_stops

        apply_crm_timer_event(setup["integration"], TIMER_STARTED, crm_timer())

        stopped = crm_timer(end=NINE + timedelta(minutes=20))
        with mock.patch("plane.utils.crm_client.CrmApiClient.get_timers", return_value=[stopped]) as get_timers:
            reconcile_crm_timer_stops()

        get_timers.assert_called_once_with([900])
        assert IssueWorkLog.objects.get(logged_by=setup["person"]).duration == 20 * 60

    def test_a_quiet_workspace_asks_the_crm_nothing(self, setup):
        from plane.bgtasks.crm_sync_task import reconcile_crm_timer_stops

        with mock.patch("plane.utils.crm_client.CrmApiClient.get_timers") as get_timers:
            reconcile_crm_timer_stops()

        get_timers.assert_not_called()
