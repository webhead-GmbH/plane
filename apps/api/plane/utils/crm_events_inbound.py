# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Apply the projects and ticket tasks made in the CRM to Plane.

Everything else in the integration starts in Plane and is mirrored out. These
two start in the CRM, because the CRM is where admins open a project for a
client and where support tickets arrive:

- ``project.saved``: a CRM project assigned to this workspace. The Plane project
  the integration already maps to that CRM id takes what this save changed in
  the CRM (``changed``: name, description) and the project's members; when there
  is none, one is created and given the mapping (the custom-field value, or the
  identifier), so everything Plane mirrors back from then on lands on that CRM
  project.
- ``task.created``: a task converted from a ticket message. It becomes a work item
  in the mapped Plane project, tied to the CRM task through ``CrmTaskLink`` — the
  same link Plane's own work items use — so from here on Plane owns it: the next
  save mirrors the work item onto that task instead of creating another.

Both are idempotent: a retried delivery finds what the first one made.
"""

# Python imports
import json
import re
import unicodedata
from datetime import date

# Third party imports
from bs4 import BeautifulSoup
from crum import impersonate

# Django imports
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone as dj_timezone
from django.utils.html import escape

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import (
    CrmIntegration,
    CrmTaskLink,
    CustomFieldValue,
    Issue,
    IssueAssignee,
    Project,
    ProjectIdentifier,
    ProjectMember,
    State,
    WorkspaceMember,
)
from plane.db.models.state import DEFAULT_STATES
from plane.utils.content_validator import validate_html_content
from plane.utils.crm_timer_inbound import plane_user_for_crm_staff

PROJECT_SAVED = "project.saved"
TASK_CREATED = "task.created"

# Plane refuses these in a project name (Project.FORBIDDEN_IDENTIFIER_CHARS_PATTERN),
# and CRM project names are full of them — "example.com – Relaunch (2026)". The
# common ones become look-alikes so the name still reads the same; the rest go.
NAME_LOOKALIKES = {
    "-": "–",
    ".": "․",
    ",": "‚",
    ":": "∶",
    "'": "’",
    "(": "[",
    ")": "]",
    "&": "＆",
    "+": "＋",
    "@": "＠",
    "#": "＃",
    "%": "％",
    "!": "ǃ",
    "?": "？",
}
NAME_DROPPED = set(";$^}{*=|<>")

IDENTIFIER_MAX_LENGTH = 12
IDENTIFIER_BASE_LENGTH = 5

# The CRM's task priorities are 1 (low) to 4 (urgent).
CRM_PRIORITY_TO_PLANE = {1: "low", 2: "medium", 3: "high", 4: "urgent"}

# CRM task statuses: 1 not started, 2 awaiting feedback, 3 testing, 4 in progress,
# 5 complete. Only the ones that mean work has begun or ended pick a state; the
# rest leave the project's default.
CRM_STATUS_TO_STATE_GROUP = {2: "started", 3: "started", 4: "started", 5: "completed"}

PLANE_PROJECT_MEMBER_ROLE = ROLE.MEMBER.value


class CrmEventError(Exception):
    """An event that cannot be applied, with a fixed code the CRM can show."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def apply_crm_event(integration, event, payload, origin=None):
    """Apply one CRM event to the integration's workspace and describe the result."""
    if event == PROJECT_SAVED:
        project = payload.get("project")
        if not isinstance(project, dict):
            raise CrmEventError("invalid_payload", "The event carries no project.")
        return apply_project_saved(integration, project)
    if event == TASK_CREATED:
        task = payload.get("task")
        if not isinstance(task, dict):
            raise CrmEventError("invalid_payload", "The event carries no task.")
        return apply_task_created(integration, task, origin=origin)
    raise CrmEventError("unsupported_event", f"Plane does not handle the event {event!r}.")


# ─── Helpers ────────────────────────────────────────────────────────────────


def _positive_int(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _plane_url(path):
    base = (settings.WEB_URL or "").rstrip("/")
    return f"{base}{path}" if base else None


def _project_url(project):
    return _plane_url(f"/{project.workspace.slug}/projects/{project.id}/issues/")


def _project_summary(project):
    return {
        "id": str(project.id),
        "name": project.name,
        "identifier": project.identifier,
        "url": _project_url(project),
    }


def clean_project_name(name):
    """A CRM project name as Plane will accept it, reading the same where it can."""
    cleaned = "".join(NAME_LOOKALIKES.get(char, "" if char in NAME_DROPPED else char) for char in str(name or ""))
    return re.sub(r"\s+", " ", cleaned).strip()[:255]


TEXT_BLOCK_TAGS = ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"]


def _plain_text(html):
    """The text of CRM HTML, one line per paragraph — Plane's project description is plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(str(html), "html.parser")
    for line_break in soup.find_all("br"):
        line_break.replace_with("\n")
    for block in soup.find_all(TEXT_BLOCK_TAGS):
        block.append("\n")
    lines = [line.strip() for line in soup.get_text("").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _locked_integration(integration):
    """Hold the integration row so two deliveries for one workspace run one after the other.

    The CRM may retry a delivery that timed out while Plane was still applying it;
    without this both would see nothing yet and each create the project or work
    item.
    """
    return CrmIntegration.objects.select_for_update().get(pk=integration.pk)


def _actor_for(integration, staff):
    """The Plane user an event is recorded as: the CRM staff member when they have
    an account in this workspace, otherwise whoever set the integration up."""
    staff = staff if isinstance(staff, dict) else {}
    user = plane_user_for_crm_staff(integration.workspace_id, _positive_int(staff.get("staff_id")), staff.get("email"))
    if user is not None:
        return user
    if (
        integration.created_by_id
        and WorkspaceMember.objects.filter(
            workspace_id=integration.workspace_id, member_id=integration.created_by_id, is_active=True
        ).exists()
    ):
        return integration.created_by
    return integration.workspace.owner


def find_project_for_crm_project(integration, crm_project_id):
    """The Plane project this workspace maps to a CRM project id, or None.

    The same mapping the Plane → CRM sync reads, run in reverse. When several
    projects carry the id, the oldest wins, so the answer never flips.
    """
    projects = Project.objects.filter(workspace_id=integration.workspace_id).order_by("created_at")
    if integration.project_mapping_source == CrmIntegration.ProjectMappingSource.IDENTIFIER:
        return projects.filter(identifier=str(crm_project_id)).first()

    if integration.crm_project_id_custom_field_id is None:
        return None
    project_ids = [
        project_id
        for project_id, value in CustomFieldValue.objects.filter(
            workspace_id=integration.workspace_id,
            custom_field_id=integration.crm_project_id_custom_field_id,
            project__isnull=False,
            issue__isnull=True,
        ).values_list("project_id", "value")
        if _positive_int(value) == crm_project_id
    ]
    return projects.filter(id__in=project_ids).first()


def _identifier_taken(workspace_id, identifier):
    return (
        Project.objects.filter(workspace_id=workspace_id, identifier=identifier).exists()
        or ProjectIdentifier.objects.filter(workspace_id=workspace_id, name=identifier).exists()
    )


def _new_identifier(workspace_id, name, crm_project_id):
    """A short, free identifier for a project made from the CRM.

    Built like the one Plane's own form suggests: the initials of the name's words,
    or its first letters when it is one word. Falls back to the CRM id when the
    name has nothing usable in Latin letters.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", ascii_name)
    if len(words) > 1:
        base = "".join(word[0] for word in words)
    else:
        base = words[0] if words else ""
    base = base.upper()[:IDENTIFIER_BASE_LENGTH] or f"CRM{crm_project_id}"[:IDENTIFIER_MAX_LENGTH]

    candidate = base
    counter = 2
    while _identifier_taken(workspace_id, candidate):
        suffix = str(counter)
        candidate = base[: IDENTIFIER_MAX_LENGTH - len(suffix)] + suffix
        counter += 1
    return candidate


def _free_project_name(workspace_id, name, crm_project_id, exclude_id=None):
    """The name, or the name marked with its CRM id when another project has it."""
    taken = Project.objects.filter(workspace_id=workspace_id)
    if exclude_id is not None:
        taken = taken.exclude(id=exclude_id)
    candidate = name
    counter = 2
    while taken.filter(name=candidate).exists():
        marker = f" [CRM {crm_project_id}]" if counter == 2 else f" [CRM {crm_project_id}-{counter - 1}]"
        candidate = name[: 255 - len(marker)] + marker
        counter += 1
    return candidate


def _ensure_project_member(project, user):
    """Add a user to the project if they never were a member. Returns True when added.

    Only ever adds: someone a Plane admin removed from the project, or who left,
    is not brought back by the next save in the CRM.
    """
    if ProjectMember.objects.filter(project=project, member=user).exists():
        return False
    workspace_role = (
        WorkspaceMember.objects.filter(workspace_id=project.workspace_id, member=user, is_active=True)
        .values_list("role", flat=True)
        .first()
    )
    if workspace_role is None:
        return False
    ProjectMember.objects.create(
        project=project,
        member=user,
        workspace_id=project.workspace_id,
        role=min(PLANE_PROJECT_MEMBER_ROLE, workspace_role),
    )
    return True


def _add_crm_members(integration, project, members):
    added = 0
    for member in members if isinstance(members, list) else []:
        if not isinstance(member, dict):
            continue
        user = plane_user_for_crm_staff(
            integration.workspace_id, _positive_int(member.get("staff_id")), member.get("email")
        )
        if user is not None and _ensure_project_member(project, user):
            added += 1
    return added


# ─── project.saved ──────────────────────────────────────────────────────────


def apply_project_saved(integration, crm_project):
    crm_project_id = _positive_int(crm_project.get("id"))
    if crm_project_id is None:
        raise CrmEventError("invalid_payload", "The project has no id.")

    mapping = integration.project_mapping_source
    if (
        mapping == CrmIntegration.ProjectMappingSource.CUSTOM_FIELD
        and integration.crm_project_id_custom_field_id is None
    ):
        raise CrmEventError(
            "mapping_not_configured",
            "Choose the custom field that holds the CRM project id in Plane's CRM sync settings first.",
        )

    name = clean_project_name(crm_project.get("name")) or f"CRM project {crm_project_id}"
    description = _plain_text(crm_project.get("description"))

    with transaction.atomic():
        integration = _locked_integration(integration)
        actor = _actor_for(integration, crm_project.get("added_by"))
        with impersonate(actor):
            project = find_project_for_crm_project(integration, crm_project_id)
            if project is None:
                project = _create_project(integration, crm_project_id, name, description, actor)
                result = "created"
            else:
                changed = crm_project.get("changed") if isinstance(crm_project.get("changed"), list) else []
                _update_project(project, crm_project_id, name, description, changed)
                result = "updated"
            members_added = _add_crm_members(integration, project, crm_project.get("members"))

    return {"result": result, "project": _project_summary(project), "members_added": members_added}


def _create_project(integration, crm_project_id, name, description, actor):
    workspace_id = integration.workspace_id

    if integration.project_mapping_source == CrmIntegration.ProjectMappingSource.IDENTIFIER:
        identifier = str(crm_project_id)
        if len(identifier) > IDENTIFIER_MAX_LENGTH or _identifier_taken(workspace_id, identifier):
            raise CrmEventError(
                "identifier_taken",
                f"Another project in this workspace already uses the identifier {identifier}.",
            )
    else:
        identifier = _new_identifier(workspace_id, name, crm_project_id)

    project = Project.objects.create(
        workspace_id=workspace_id,
        name=_free_project_name(workspace_id, name, crm_project_id),
        identifier=identifier,
        description=description,
    )
    ProjectIdentifier.objects.create(name=project.identifier, project=project, workspace_id=workspace_id)
    ProjectMember.objects.create(project=project, member=actor, workspace_id=workspace_id, role=ROLE.ADMIN.value)
    State.objects.bulk_create(
        [
            State(
                name=state["name"],
                color=state["color"],
                project=project,
                sequence=state["sequence"],
                workspace_id=workspace_id,
                group=state["group"],
                default=state.get("default", False),
                created_by=actor,
            )
            for state in DEFAULT_STATES
        ]
    )

    if integration.project_mapping_source == CrmIntegration.ProjectMappingSource.CUSTOM_FIELD:
        CustomFieldValue.objects.create(
            workspace_id=workspace_id,
            project=project,
            custom_field_id=integration.crm_project_id_custom_field_id,
            value=str(crm_project_id),
        )
    return project


def _update_project(project, crm_project_id, name, description, changed_in_crm):
    """Carry over the name and description the CRM just changed.

    Only what this save changed in the CRM (``changed_in_crm``) is applied. The
    project may have existed in Plane, under its own name, long before the CRM
    project was given this workspace — and merely linking it must not rename it
    or wipe its description. A rename made in the CRM after that still comes
    through. The identifier is never touched: work item keys are built from it.
    """
    fields = []
    if "name" in changed_in_crm:
        new_name = (
            name
            if name == project.name
            else _free_project_name(project.workspace_id, name, crm_project_id, exclude_id=project.id)
        )
        if new_name != project.name:
            project.name = new_name
            fields.append("name")
    if "description" in changed_in_crm and description != (project.description or ""):
        project.description = description
        fields.append("description")
    if fields:
        project.save(update_fields=[*fields, "updated_at", "updated_by"])


# ─── task.created ───────────────────────────────────────────────────────────


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _state_for(project, crm_status):
    """The state for a CRM status, or None to let the project's default apply."""
    group = CRM_STATUS_TO_STATE_GROUP.get(_positive_int(crm_status))
    if group is None:
        return None
    return State.objects.filter(project=project, group=group).order_by("sequence").first()


def _description_html(task):
    """The task's text, sanitised, with a note of the ticket it came from."""
    html = str(task.get("description") or "").strip()
    if html:
        is_valid, _error, sanitized = validate_html_content(html)
        html = sanitized if sanitized is not None else html
        if not is_valid:
            html = f"<p>{escape(_plain_text(html))}</p>"

    ticket = task.get("ticket") if isinstance(task.get("ticket"), dict) else {}
    ticket_id = _positive_int(ticket.get("id"))
    if ticket_id:
        label = escape(f"#{ticket_id} {ticket.get('subject') or ''}".strip())
        url = str(ticket.get("url") or "")
        reference = f'<a href="{escape(url)}">{label}</a>' if url.startswith(("http://", "https://")) else label
        html += f"<p>From CRM ticket {reference}</p>"
    return html or "<p></p>"


def _work_item_summary(issue):
    from plane.bgtasks.crm_sync_task import _work_item_url

    return {
        "id": str(issue.id),
        "identifier": f"{issue.project.identifier}-{issue.sequence_id}",
        "name": issue.name,
        "url": _work_item_url(issue),
    }


def apply_task_created(integration, task, origin=None):
    crm_task_id = _positive_int(task.get("id"))
    crm_project_id = _positive_int(task.get("project_id"))
    if crm_task_id is None:
        raise CrmEventError("invalid_payload", "The task has no id.")
    if crm_project_id is None:
        raise CrmEventError("no_project", "The task belongs to no CRM project.")

    with transaction.atomic():
        integration = _locked_integration(integration)

        link = (
            CrmTaskLink.objects.filter(workspace_id=integration.workspace_id, crm_task_id=crm_task_id)
            .select_related("issue__project", "issue__workspace")
            .first()
        )
        if link is not None:
            return {"result": "exists", "work_item": _work_item_summary(link.issue)}

        project = find_project_for_crm_project(integration, crm_project_id)
        if project is None:
            raise CrmEventError(
                "project_not_linked", "No Plane project in this workspace is linked to that CRM project."
            )
        if project.archived_at is not None:
            raise CrmEventError("project_archived", f"The Plane project {project.name} is archived.")

        actor = _actor_for(integration, task.get("added_by"))
        start_date = _parse_date(task.get("startdate"))
        target_date = _parse_date(task.get("duedate"))
        if start_date and target_date and start_date > target_date:
            start_date = None

        with impersonate(actor):
            _ensure_project_member(project, actor)
            issue = Issue.objects.create(
                project=project,
                workspace_id=project.workspace_id,
                name=(str(task.get("name") or "").strip() or f"CRM task {crm_task_id}")[:255],
                description_html=_description_html(task),
                priority=CRM_PRIORITY_TO_PLANE.get(_positive_int(task.get("priority")), "none"),
                state=_state_for(project, task.get("status")),
                start_date=start_date,
                target_date=target_date,
            )
            for assignee in task.get("assignees") if isinstance(task.get("assignees"), list) else []:
                if not isinstance(assignee, dict):
                    continue
                user = plane_user_for_crm_staff(
                    integration.workspace_id, _positive_int(assignee.get("staff_id")), assignee.get("email")
                )
                if user is None:
                    continue
                _ensure_project_member(project, user)
                IssueAssignee.objects.get_or_create(
                    issue=issue, assignee=user, defaults={"project": project, "workspace_id": project.workspace_id}
                )

        CrmTaskLink.objects.create(
            workspace_id=integration.workspace_id,
            issue=issue,
            crm_task_id=crm_task_id,
            crm_project_id=crm_project_id,
            last_synced_at=dj_timezone.now(),
        )
        _record_creation(issue, actor, task, origin)

    issue = Issue.objects.select_related("project", "workspace").get(pk=issue.pk)
    return {"result": "created", "work_item": _work_item_summary(issue)}


def _record_creation(issue, actor, task, origin):
    """Put "created the work item" in the history, as the app's own create does."""
    from plane.bgtasks.issue_activities_task import issue_activity

    requested = {"name": issue.name, "crm_task_id": task.get("id")}
    transaction.on_commit(
        lambda: issue_activity.delay(
            type="issue.activity.created",
            requested_data=json.dumps(requested, cls=DjangoJSONEncoder),
            actor_id=str(actor.id),
            issue_id=str(issue.id),
            project_id=str(issue.project_id),
            current_instance=None,
            epoch=int(dj_timezone.now().timestamp()),
            notification=True,
            origin=origin,
        )
    )
