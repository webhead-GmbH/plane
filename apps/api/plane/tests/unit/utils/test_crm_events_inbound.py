# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Projects and ticket tasks made in the CRM, arriving in Plane."""

# Python imports
import hashlib
import hmac
import json
import time
from unittest import mock
from uuid import uuid4

# Third-party imports
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

# Module imports
from plane.db.models import (
    CrmIntegration,
    CrmTaskLink,
    CustomField,
    CustomFieldValue,
    Issue,
    IssueAssignee,
    Project,
    ProjectMember,
    State,
)
from plane.tests.factories import ProjectFactory, UserFactory, WorkspaceFactory, WorkspaceMemberFactory
from plane.utils.crm_events_inbound import (
    PROJECT_SAVED,
    TASK_CREATED,
    CrmEventError,
    apply_project_saved,
    apply_task_created,
    clean_project_name,
)
from plane.utils.crm_timer_webhook import register_timer_webhook

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

SECRET = "s" * 64
CRM_PROJECT_ID = 12
CRM_TASK_ID = 640


@pytest.fixture
def setup():
    """A workspace whose CRM integration maps projects through a custom field."""
    owner = UserFactory(username=uuid4().hex, email="owner@example.com")
    workspace = WorkspaceFactory(owner=owner)
    WorkspaceMemberFactory(workspace=workspace, member=owner, role=20)
    person = UserFactory(username=uuid4().hex, email="person@example.com")
    WorkspaceMemberFactory(workspace=workspace, member=person, role=15)
    field = CustomField.objects.create(
        workspace=workspace,
        entity_type="project",
        display_name="CRM project ID",
        key="crm_project_id",
        field_type="text",
    )
    integration = CrmIntegration(
        workspace=workspace,
        crm_api_url="https://crm.example.com",
        crm_project_id_custom_field=field,
        created_by=owner,
    )
    integration.set_api_key("key")
    integration.save(created_by_id=owner.id)
    return {"workspace": workspace, "owner": owner, "person": person, "field": field, "integration": integration}


def crm_project(**overrides):
    project = {
        "id": CRM_PROJECT_ID,
        "name": "example.com - Relaunch (2026)",
        "description": "<p>New <b>site</b> for the client.</p>",
        "added_by": {"staff_id": 1, "email": "owner@example.com"},
        "members": [],
    }
    project.update(overrides)
    return project


def crm_task(**overrides):
    task = {
        "id": CRM_TASK_ID,
        "project_id": CRM_PROJECT_ID,
        "name": "Contact form sends nothing",
        "description": "<p>The form on /contact returns an error.</p>",
        "priority": 3,
        "status": 1,
        "startdate": "2026-10-21",
        "duedate": "2026-10-24",
        "added_by": {"staff_id": 1, "email": "owner@example.com"},
        "assignees": [{"staff_id": 7, "email": "person@example.com"}],
        "ticket": {
            "id": 33,
            "subject": "Contact form broken",
            "url": "https://crm.example.com/admin/tickets/ticket/33",
        },
    }
    task.update(overrides)
    return task


def mapped_project(setup, crm_id=CRM_PROJECT_ID, **kwargs):
    project = ProjectFactory(workspace=setup["workspace"], **kwargs)
    CustomFieldValue.objects.create(
        workspace=setup["workspace"], project=project, custom_field=setup["field"], value=str(crm_id)
    )
    return project


class TestProjectSaved:
    def test_creates_the_project_and_maps_it_to_the_crm_project(self, setup):
        result = apply_project_saved(setup["integration"], crm_project())

        assert result["result"] == "created"
        project = Project.objects.get(id=result["project"]["id"])
        assert project.name == clean_project_name("example.com - Relaunch (2026)")
        assert project.description == "New site for the client."
        assert CustomFieldValue.objects.get(project=project, custom_field=setup["field"]).value == str(CRM_PROJECT_ID)
        assert State.objects.filter(project=project).count() > 0
        assert ProjectMember.objects.filter(project=project, member=setup["owner"], role=20).exists()
        assert project.created_by == setup["owner"]

    def test_a_rename_in_the_crm_renames_the_same_project(self, setup):
        first = apply_project_saved(setup["integration"], crm_project())

        second = apply_project_saved(setup["integration"], crm_project(name="Relaunch phase two", changed=["name"]))

        assert second["result"] == "updated"
        assert second["project"]["id"] == first["project"]["id"]
        assert Project.objects.filter(workspace=setup["workspace"]).count() == 1
        assert Project.objects.get(id=first["project"]["id"]).name == "Relaunch phase two"

    def test_a_project_plane_already_maps_to_that_crm_project_is_reused(self, setup):
        existing = mapped_project(setup, name="Already here", identifier="HERE")

        result = apply_project_saved(setup["integration"], crm_project(name="Already here"))

        assert result["result"] == "updated"
        assert result["project"]["id"] == str(existing.id)
        assert result["project"]["identifier"] == "HERE"

    def test_linking_a_project_that_existed_in_plane_keeps_its_name_and_description(self, setup):
        existing = mapped_project(setup, name="QA Test", identifier="QATEST", description="Kept as it is")

        apply_project_saved(setup["integration"], crm_project(name="Project 1", description=""))

        existing.refresh_from_db()
        assert existing.name == "QA Test"
        assert existing.description == "Kept as it is"

    def test_only_what_changed_in_the_crm_is_carried_over(self, setup):
        existing = mapped_project(setup, name="Shop", identifier="SHOP", description="Written in Plane")

        apply_project_saved(
            setup["integration"], crm_project(name="Shop 2027", description="<p>From the CRM</p>", changed=["name"])
        )

        existing.refresh_from_db()
        assert existing.name == "Shop 2027"
        assert existing.description == "Written in Plane"

    def test_identifier_mapping_uses_the_crm_id_as_the_identifier(self, setup):
        setup["integration"].project_mapping_source = CrmIntegration.ProjectMappingSource.IDENTIFIER
        setup["integration"].save()

        result = apply_project_saved(setup["integration"], crm_project())

        assert result["project"]["identifier"] == str(CRM_PROJECT_ID)
        assert not CustomFieldValue.objects.filter(project_id=result["project"]["id"]).exists()

    def test_custom_field_mapping_without_a_field_is_refused(self, setup):
        setup["integration"].crm_project_id_custom_field = None
        setup["integration"].save()

        with pytest.raises(CrmEventError) as error:
            apply_project_saved(setup["integration"], crm_project())

        assert error.value.code == "mapping_not_configured"
        assert not Project.objects.filter(workspace=setup["workspace"]).exists()

    def test_a_name_another_project_has_is_marked_with_the_crm_id(self, setup):
        ProjectFactory(workspace=setup["workspace"], name="Shop", identifier="SHOP")

        result = apply_project_saved(setup["integration"], crm_project(name="Shop"))

        assert result["project"]["name"] == f"Shop [CRM {CRM_PROJECT_ID}]"
        assert result["project"]["identifier"] != "SHOP"

    def test_crm_members_with_a_plane_account_join_the_project(self, setup):
        members = [{"staff_id": 7, "email": "person@example.com"}, {"staff_id": 8, "email": "nobody@example.com"}]

        result = apply_project_saved(setup["integration"], crm_project(members=members))

        assert result["members_added"] == 1
        assert ProjectMember.objects.filter(project_id=result["project"]["id"], member=setup["person"]).exists()

    def test_someone_removed_in_plane_is_not_added_back(self, setup):
        members = [{"staff_id": 7, "email": "person@example.com"}]
        result = apply_project_saved(setup["integration"], crm_project(members=members))
        ProjectMember.objects.filter(project_id=result["project"]["id"], member=setup["person"]).update(is_active=False)

        again = apply_project_saved(setup["integration"], crm_project(members=members))

        assert again["members_added"] == 0
        assert not ProjectMember.objects.get(project_id=result["project"]["id"], member=setup["person"]).is_active


class TestProjectNames:
    @pytest.mark.parametrize(
        "crm_name",
        ["example.com - Relaunch (2026)", "Müller & Söhne: Shop!", "A+B #1 @home 50% done?", "x;y$z{w}"],
    )
    def test_plane_accepts_the_cleaned_name(self, crm_name):
        import re

        assert not re.match(Project.FORBIDDEN_IDENTIFIER_CHARS_PATTERN, clean_project_name(crm_name))


class TestTaskCreated:
    def test_creates_a_linked_work_item_in_the_mapped_project(self, setup):
        project = mapped_project(setup, name="Site", identifier="SITE")
        State.objects.create(
            name="Todo", project=project, workspace=setup["workspace"], group="unstarted", default=True
        )

        result = apply_task_created(setup["integration"], crm_task())

        assert result["result"] == "created"
        issue = Issue.objects.get(id=result["work_item"]["id"])
        assert issue.project == project
        assert issue.name == "Contact form sends nothing"
        assert issue.priority == "high"
        assert str(issue.start_date) == "2026-10-21" and str(issue.target_date) == "2026-10-24"
        assert "Contact form broken" in issue.description_html
        assert "tickets/ticket/33" in issue.description_html
        assert CrmTaskLink.objects.get(issue=issue).crm_task_id == CRM_TASK_ID
        assert IssueAssignee.objects.filter(issue=issue, assignee=setup["person"]).exists()
        assert ProjectMember.objects.filter(project=project, member=setup["person"]).exists()
        assert result["work_item"]["identifier"] == f"SITE-{issue.sequence_id}"

    def test_a_task_in_progress_starts_in_a_started_state(self, setup):
        project = mapped_project(setup, name="Site", identifier="SITE")
        State.objects.create(
            name="Todo", project=project, workspace=setup["workspace"], group="unstarted", default=True
        )
        doing = State.objects.create(name="Doing", project=project, workspace=setup["workspace"], group="started")

        result = apply_task_created(setup["integration"], crm_task(status=4))

        assert Issue.objects.get(id=result["work_item"]["id"]).state == doing

    def test_a_repeated_delivery_creates_nothing_new(self, setup):
        mapped_project(setup, name="Site", identifier="SITE")
        first = apply_task_created(setup["integration"], crm_task())

        second = apply_task_created(setup["integration"], crm_task())

        assert second["result"] == "exists"
        assert second["work_item"]["id"] == first["work_item"]["id"]
        assert Issue.objects.filter(workspace=setup["workspace"]).count() == 1

    def test_a_crm_project_with_no_plane_project_is_refused(self, setup):
        with pytest.raises(CrmEventError) as error:
            apply_task_created(setup["integration"], crm_task())

        assert error.value.code == "project_not_linked"

    def test_a_task_with_no_project_is_refused(self, setup):
        with pytest.raises(CrmEventError) as error:
            apply_task_created(setup["integration"], crm_task(project_id=None))

        assert error.value.code == "no_project"

    def test_an_archived_project_is_refused(self, setup):
        mapped_project(setup, name="Old", identifier="OLD", archived_at=timezone.now())

        with pytest.raises(CrmEventError) as error:
            apply_task_created(setup["integration"], crm_task())

        assert error.value.code == "project_archived"
        assert not Issue.objects.filter(workspace=setup["workspace"]).exists()


class TestEventsWebhook:
    def post(self, setup, payload, secret=SECRET):
        body = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return APIClient().post(
            f"/api/workspaces/{setup['workspace'].slug}/crm-integration/events/",
            data=body,
            content_type="application/json",
            HTTP_X_PLANE_API_SIGNATURE=signature,
        )

    def with_secret(self, setup):
        from plane.license.utils.encryption import encrypt_data

        setup["integration"].timer_webhook_secret_encrypted = encrypt_data(SECRET)
        setup["integration"].save(update_fields=["timer_webhook_secret_encrypted"])

    def test_a_signed_project_event_creates_the_project(self, setup):
        self.with_secret(setup)

        response = self.post(setup, {"event": PROJECT_SAVED, "sent_at": int(time.time()), "project": crm_project()})

        assert response.status_code == 200
        assert response.json()["result"] == "created"
        assert Project.objects.filter(workspace=setup["workspace"]).count() == 1

    def test_an_event_that_cannot_be_applied_says_why(self, setup):
        self.with_secret(setup)

        response = self.post(setup, {"event": TASK_CREATED, "sent_at": int(time.time()), "task": crm_task()})

        assert response.status_code == 422
        assert response.json()["code"] == "project_not_linked"

    def test_an_unknown_event_is_refused(self, setup):
        self.with_secret(setup)

        response = self.post(setup, {"event": "invoice.paid", "sent_at": int(time.time())})

        assert response.status_code == 422
        assert response.json()["code"] == "unsupported_event"

    def test_a_wrong_signature_is_refused(self, setup):
        self.with_secret(setup)

        response = self.post(
            setup, {"event": PROJECT_SAVED, "sent_at": int(time.time()), "project": crm_project()}, secret="x" * 64
        )

        assert response.status_code == 401
        assert not Project.objects.filter(workspace=setup["workspace"]).exists()


class TestRegistration:
    def test_the_crm_learns_the_workspace_and_where_to_send_its_events(self, setup, settings):
        settings.CRM_WEBHOOK_BASE_URL = "https://plane.example.com"

        with mock.patch("plane.utils.crm_client.CrmApiClient._request", return_value={"data": {}}) as request:
            assert register_timer_webhook(setup["integration"]) == (True, None)

        body = request.call_args.kwargs["json"]
        slug = setup["workspace"].slug
        assert body["workspace_slug"] == slug
        assert body["workspace_name"] == setup["workspace"].name
        assert body["events_url"] == f"https://plane.example.com/api/workspaces/{slug}/crm-integration/events/"

    def test_deleting_the_integration_unregisters_it(self, setup):
        client = APIClient()
        client.force_authenticate(user=setup["owner"])

        with mock.patch("plane.utils.crm_client.CrmApiClient._request", return_value={"data": {}}) as request:
            response = client.delete(f"/api/workspaces/{setup['workspace'].slug}/crm-integration/")

        assert response.status_code == 204
        assert request.call_args.args == ("DELETE", "timer_webhook")
        assert not CrmIntegration.objects.filter(workspace=setup["workspace"]).exists()
