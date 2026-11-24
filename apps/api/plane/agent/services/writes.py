# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Changing things in Plane on a person's behalf.

Everything here goes through the same serializers, models and background tasks the rest
of Plane uses, so a work item made by an app is indistinguishable from one made in the
web app: it gets its sequence number, its activity entry, its notifications, its
webhooks. The app is not given a second, looser way in.

What this module adds is *narrowness*. Input is checked field by field against a short
list and anything else is refused (an app cannot set `created_by`, `is_draft` or a
description's binary form by naming it); text from the app is turned into HTML only after
being escaped; and who may do what is decided from the person's role in the project, at
the moment of the call.
"""

# Python imports
import html
import json
import re
from datetime import date as date_type
from datetime import datetime, time

# Django imports
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

# Module imports
from plane.agent import conf
from plane.agent.errors import AgentError, forbidden, invalid_request, not_found
from plane.agent.services import dates, work_items
from plane.api.serializers import IssueCommentCreateSerializer, IssueCommentSerializer, IssueSerializer
from plane.app.permissions import ROLE
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import Issue, IssueComment, IssueDescriptionVersion, IssueWorkLog, ProjectMember
from plane.hr.services.settled import settled_month_for
from plane.hr.utils.calendar import hr_timezone
from plane.utils.host import base_host
from plane.utils.work_timer import state_move_blocked_by_timer

WRITE_ROLES = (ROLE.ADMIN.value, ROLE.MEMBER.value)
ANY_ROLE = (ROLE.ADMIN.value, ROLE.MEMBER.value, ROLE.GUEST.value)
PRIORITIES = ("urgent", "high", "medium", "low", "none")

MAX_NAME = 255
MAX_DESCRIPTION = 20000
# The whole description once text is added to it, as stored (HTML): the editor refuses documents far smaller than this.
MAX_DESCRIPTION_HTML = 200_000
MAX_COMMENT = 10000
MAX_NOTE = 500
MAX_PEOPLE = 20
MAX_LABELS = 20


# --- Reading what the app sent -----------------------------------------------


def require_object(data):
    if not isinstance(data, dict):
        raise invalid_request("The request body must be a JSON object.")
    return data


def only_fields(data, allowed):
    """Refuse anything the app was not meant to set, rather than quietly ignoring or accepting it."""
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise invalid_request(f"Unknown field(s): {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}.")


def text_field(data, name, *, max_length, required=False, allow_empty=False):
    value = data.get(name)
    if value is None:
        if required:
            raise invalid_request(f"{name} is required.")
        return None
    if not isinstance(value, str):
        raise invalid_request(f"{name} must be a string.")
    value = value.replace("\x00", "").strip()
    if not value and not allow_empty:
        if required:
            raise invalid_request(f"{name} must not be empty.")
        return None
    if len(value) > max_length:
        raise invalid_request(f"{name} must be at most {max_length} characters.")
    return value


def id_list(data, name, *, limit):
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > limit:
        raise invalid_request(f"{name} must be a list of at most {limit} ids.")
    return [str(work_items.parse_uuid(item, name)) for item in value]


def choice_field(data, name, allowed):
    value = data.get(name)
    if value is None:
        return None
    if value not in allowed:
        raise invalid_request(f"{name} must be one of: {', '.join(allowed)}.")
    return value


def date_field(data, name):
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise invalid_request(f"{name} must be a date written YYYY-MM-DD.")
    return dates.parse_date(value, name)


def text_to_html(text):
    """Plain text as safe HTML: every character escaped, blank lines between paragraphs, single line breaks kept.

    Nothing the app sends is ever treated as markup. A model asked to "write a description"
    can produce `<script>`; here it becomes the visible text `<script>`.
    """
    paragraphs = [part for part in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n") if part.strip()]
    return "".join(f"<p>{html.escape(part.strip()).replace(chr(10), '<br>')}</p>" for part in paragraphs)


# --- Who may do what ----------------------------------------------------------


def role_in(user, project_id):
    return (
        ProjectMember.objects.filter(project_id=project_id, member=user, is_active=True)
        .values_list("role", flat=True)
        .first()
    )


def writable_project(user, slug, project_id, roles=WRITE_ROLES):
    """A project the person may change things in.

    A project they are not in answers like one that does not exist. One they are in, but
    only as a guest, says so: they can already see it, so there is nothing to hide.
    """
    project = (
        work_items.visible_projects(user)
        .filter(pk=work_items.parse_uuid(project_id, "project_id"), workspace__slug=slug)
        .select_related("workspace")
        .first()
    )
    if project is None:
        raise not_found("No such project, or you are not a member of it.")
    if role_in(user, project.id) not in roles:
        raise forbidden("Your role in this project does not allow this.")
    return project


def writable_issue(user, slug, ref, roles=WRITE_ROLES):
    """A work item the person can see and may change, with the project role they hold in it."""
    issue = work_items.resolve(user, slug, ref)
    if issue is None:
        raise not_found()
    if role_in(user, issue.project_id) not in roles:
        raise forbidden("Your role in this project does not allow this.")
    return issue


# --- Work items ---------------------------------------------------------------

CREATE_FIELDS = ("name", "description", "priority", "state", "assignees", "labels", "start_date", "target_date")
UPDATE_FIELDS = (
    "name",
    "description",
    "description_append",
    "expected_description_version",
    "priority",
    "state",
    "start_date",
    "target_date",
    "add_assignees",
    "remove_assignees",
    "add_labels",
    "remove_labels",
)


def _validation_error(serializer):
    return AgentError(
        "invalid_request",
        "Some fields are not valid.",
        extra={"fields": json.loads(json.dumps(serializer.errors, cls=DjangoJSONEncoder))},
    )


def parse_create(data):
    data = require_object(data)
    only_fields(data, CREATE_FIELDS)
    fields = {
        "name": text_field(data, "name", max_length=MAX_NAME, required=True),
        "priority": choice_field(data, "priority", PRIORITIES),
        "state": str(work_items.parse_uuid(data["state"], "state")) if data.get("state") else None,
        "assignees": id_list(data, "assignees", limit=MAX_PEOPLE),
        "labels": id_list(data, "labels", limit=MAX_LABELS),
        "start_date": date_field(data, "start_date"),
        "target_date": date_field(data, "target_date"),
    }
    description = text_field(data, "description", max_length=MAX_DESCRIPTION)
    if description:
        fields["description_html"] = text_to_html(description)
    return {key: value for key, value in fields.items() if value is not None}


def _serializer_input(fields):
    """The public API's serializer takes dates as text."""
    return {key: (value.isoformat() if isinstance(value, date_type) else value) for key, value in fields.items()}


def check_create(project, fields):
    """Validate a new work item and return the serializer, ready to save."""
    serializer = IssueSerializer(
        data=_serializer_input(fields),
        context={
            "project_id": project.id,
            "workspace_id": project.workspace_id,
            "default_assignee_id": project.default_assignee_id,
        },
    )
    if not serializer.is_valid():
        raise _validation_error(serializer)
    return serializer


def create_work_item(request, user, project, fields):
    """Create a work item exactly as the web app would, and tell the activity and webhook pipelines."""
    serializer = check_create(project, fields)
    serializer.save()
    issue_id = str(serializer.data["id"])

    requested = {
        key: value
        for key, value in {
            "name": fields["name"],
            "priority": fields.get("priority"),
            "state_id": fields.get("state"),
            "assignee_ids": fields.get("assignees"),
            "label_ids": fields.get("labels"),
            "description_html": fields.get("description_html"),
            "start_date": fields["start_date"].isoformat() if fields.get("start_date") else None,
            "target_date": fields["target_date"].isoformat() if fields.get("target_date") else None,
        }.items()
        if value is not None
    }
    origin = base_host(request=request, is_app=True)
    issue_activity.delay(
        type="issue.activity.created",
        requested_data=json.dumps(requested, cls=DjangoJSONEncoder),
        actor_id=str(user.id),
        issue_id=issue_id,
        project_id=str(project.id),
        current_instance=None,
        epoch=int(timezone.now().timestamp()),
        notification=True,
        origin=origin,
    )
    model_activity.delay(
        model_name="issue",
        model_id=issue_id,
        requested_data=requested,
        current_instance=None,
        actor_id=user.id,
        slug=project.workspace.slug,
        origin=origin,
    )
    return issue_id


def parse_update(data):
    data = require_object(data)
    only_fields(data, UPDATE_FIELDS)
    fields = {
        "name": text_field(data, "name", max_length=MAX_NAME),
        "priority": choice_field(data, "priority", PRIORITIES),
        "state": str(work_items.parse_uuid(data["state"], "state")) if data.get("state") else None,
        "add_assignees": id_list(data, "add_assignees", limit=MAX_PEOPLE),
        "remove_assignees": id_list(data, "remove_assignees", limit=MAX_PEOPLE),
        "add_labels": id_list(data, "add_labels", limit=MAX_LABELS),
        "remove_labels": id_list(data, "remove_labels", limit=MAX_LABELS),
    }
    # A date can be cleared by sending null, so absence and null are different here.
    for name in ("start_date", "target_date"):
        if name in data:
            fields[name] = date_field(data, name) or "clear"
    fields.update(_parse_description_edit(data))
    fields = {key: value for key, value in fields.items() if value is not None}
    if not fields:
        raise invalid_request("Nothing to change. Send at least one of: " + ", ".join(UPDATE_FIELDS) + ".")
    return fields


def _parse_description_edit(data):
    """How the description is to change: text added to the end, or the whole of it replaced.

    Adding keeps everything already there (formatting, images, links). Replacing does not, and an app
    only ever sees the description as plain text, so it must say which version it read; if the work
    item's description is not that any more somebody changed it in between, and the edit is refused.
    """
    append, replace = "description_append" in data, "description" in data
    if append and replace:
        raise invalid_request("Send either description (replace it) or description_append (add to it), not both.")
    if not (append or replace):
        if "expected_description_version" in data:
            raise invalid_request("expected_description_version goes with description or description_append.")
        return {}

    name = "description_append" if append else "description"
    text = text_field(data, name, max_length=MAX_DESCRIPTION)
    if not text:
        raise invalid_request(f"{name} must not be empty.")
    fields = {name: text}

    expected = data.get("expected_description_version")
    if expected is not None:
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{16}", expected):
            raise invalid_request("expected_description_version must be the description_version you read.")
        fields["expected_description_version"] = expected
    elif replace:
        raise invalid_request(
            "Replacing a description needs expected_description_version: the description_version of the work item "
            "as you read it. Read it first, or add to the description with description_append instead."
        )
    return fields


def check_description_version(issue, fields):
    """Refuse an edit made on top of a description that is no longer the one the app read."""
    expected = fields.get("expected_description_version")
    current = work_items.description_version(issue.description_html)
    if expected and expected != current:
        raise AgentError(
            "description_changed",
            "The description changed after you read it. Read the work item again and edit what is there now.",
            status_code=409,
            extra={"description_version": current},
        )


_EMPTY_BODY = re.compile(r"<(img|image-component|a|ul|ol|table|pre|blockquote)\b", re.IGNORECASE)
_NOT_PLAIN = re.compile(r"<(?!/?(?:p|br)\b)[a-zA-Z]")


def _is_empty_description(current_html):
    """A description the editor left as an empty paragraph is nothing to add to."""
    if _EMPTY_BODY.search(current_html or ""):
        return False
    return not re.sub(r"<[^>]*>", "", current_html or "").strip()


def description_after(current_html, fields):
    """The stored description once the edit is made."""
    if "description" in fields:
        return text_to_html(fields["description"])
    added = text_to_html(fields["description_append"])
    if _is_empty_description(current_html):
        return added
    return (current_html or "") + added


def _current_ids(issue):
    return (
        sorted(str(person.id) for person in work_items.assignees_of(issue)),
        sorted(str(label.id) for label in work_items.labels_of(issue)),
    )


def plan_update(issue, fields):
    """What the work item will look like, as `{field: (from, to)}` plus the serializer input to get there."""
    current_assignees, current_labels = _current_ids(issue)
    wanted = {}
    changes = {}

    def change(name, before, after, key=None):
        if before != after:
            wanted[key or name] = after
            changes[name] = {"from": before, "to": after}

    if "name" in fields:
        change("name", issue.name, fields["name"])
    if "priority" in fields:
        change("priority", issue.priority, fields["priority"])
    if "state" in fields:
        change("state", str(issue.state_id) if issue.state_id else None, fields["state"])
    for name in ("start_date", "target_date"):
        if name in fields:
            after = None if fields[name] == "clear" else fields[name].isoformat()
            before = getattr(issue, name).isoformat() if getattr(issue, name) else None
            change(name, before, after)
    if "description" in fields or "description_append" in fields:
        check_description_version(issue, fields)
        before_html = issue.description_html or ""
        after_html = description_after(before_html, fields)
        if len(after_html) > MAX_DESCRIPTION_HTML:
            raise invalid_request("The description would become too long. Add less, or put the rest in a comment.")
        if before_html != after_html:
            wanted["description_html"] = after_html
            if "description" in fields:
                changes["description"] = {
                    "mode": "replace",
                    "from": work_items.plain_text(before_html),
                    "to": fields["description"],
                    # Anything but plain paragraphs (images, links, lists, headings) is lost by replacing.
                    "drops_formatting": bool(_NOT_PLAIN.search(before_html)),
                }
            else:
                changes["description"] = {"mode": "append", "added": fields["description_append"]}
    if "add_assignees" in fields or "remove_assignees" in fields:
        after = (set(current_assignees) | set(fields.get("add_assignees", []))) - set(
            fields.get("remove_assignees", [])
        )
        change("assignees", current_assignees, sorted(after), key="assignees")
    if "add_labels" in fields or "remove_labels" in fields:
        added, removed = set(fields.get("add_labels", [])), set(fields.get("remove_labels", []))
        after = (set(current_labels) | added) - removed
        change("labels", current_labels, sorted(after), key="labels")
    return wanted, changes


def _update_serializer(issue, wanted, project):
    # Not given the description: the serializer parses HTML and wraps several paragraphs in a `<div>`, so
    # every addition would nest the whole description one level deeper. It is stored by `_store_description`.
    return IssueSerializer(
        issue,
        data={key: value for key, value in wanted.items() if key != "description_html"},
        context={"project_id": project.id, "workspace_id": project.workspace_id},
        partial=True,
    )


def _store_description(issue, new_html):
    """Store the new description.

    The HTML here is the old description, which Plane stored itself, with paragraphs of escaped text added
    or put in its place, so there is nothing in it to sanitise. The editor keeps a document of its own beside
    the HTML. Left as it was, the next person to open the work item would see the old text and, typing,
    replace the edit; emptied, it is made again from the HTML, which is what already happens for a work item
    created through the API.
    """
    Issue.objects.filter(pk=issue.pk).update(
        description_html=new_html,
        description_stripped=strip_tags(new_html) if new_html else None,
        description_binary=None,
        description_json={},
    )


def _keep_description_version(issue, user, *, before, replacing=False):
    """Put the description in the work item's version history, so an edit can be undone from Plane.

    Before replacing, the old text is saved if the history does not already end with exactly it; after
    any edit, the new text is. Written here rather than through the background task the web app uses,
    which folds a person's saves within ten minutes into one and would fold the old text away.
    """
    if before:
        if not replacing:
            return
        latest = IssueDescriptionVersion.objects.filter(issue_id=issue.pk).order_by("-last_saved_at").first()
        if latest is not None and latest.description_html == issue.description_html:
            return
    IssueDescriptionVersion.log_issue_description_version(issue, user.id)


def update_work_item(request, user, issue, fields, *, apply=True):
    """Change a work item. Returns `{field: {from, to}}`; with `apply=False` it only checks.

    Moving a work item to a state where time cannot be tracked is refused while a timer is
    running on it, exactly as in the web app.
    """
    wanted, changes = plan_update(issue, fields)
    if not changes:
        return {}

    project = issue.project
    if "state" in wanted:
        from plane.db.models import State

        new_state = State.objects.filter(pk=wanted["state"], project_id=project.id).first()
        if new_state is None:
            raise invalid_request("state is not a state of this work item's project.", fields={"state": "unknown"})
        if state_move_blocked_by_timer(issue, new_state):
            raise AgentError(
                "timer_running",
                "Stop the running timer before moving this work item to a state where time cannot be tracked.",
                status_code=409,
            )

    serializer = _update_serializer(issue, wanted, project)
    if not serializer.is_valid():
        raise _validation_error(serializer)
    if not apply:
        return changes

    with transaction.atomic():
        stored = None
        if "description_html" in wanted:
            # The description is read again under a lock, so two edits at once cannot both think they were
            # made on the description they read, and the version check is made on what is really stored.
            stored = Issue.objects.select_for_update(of=("self",)).get(pk=issue.pk)
            issue.description_html = stored.description_html
            wanted, changes = plan_update(issue, fields)
            if not changes:
                return {}
            serializer = _update_serializer(issue, wanted, project)
            if not serializer.is_valid():
                raise _validation_error(serializer)
            _keep_description_version(stored, user, before=True, replacing="description" in fields)

        current_assignees, current_labels = _current_ids(issue)
        before = {
            "name": issue.name,
            "priority": issue.priority,
            "state_id": str(issue.state_id) if issue.state_id else None,
            "start_date": issue.start_date.isoformat() if issue.start_date else None,
            "target_date": issue.target_date.isoformat() if issue.target_date else None,
            "assignee_ids": current_assignees,
            "label_ids": current_labels,
        }
        if "description_html" in wanted:
            before["description_html"] = issue.description_html
        current_instance = json.dumps(before, cls=DjangoJSONEncoder)
        serializer.save()

        if "description_html" in wanted:
            _store_description(issue, wanted["description_html"])
            _keep_description_version(Issue.objects.get(pk=issue.pk), user, before=False)

    requested = {
        {"state": "state_id", "assignees": "assignee_ids", "labels": "label_ids"}.get(key, key): value
        for key, value in wanted.items()
    }
    origin = base_host(request=request, is_app=True)
    issue_activity.delay(
        type="issue.activity.updated",
        requested_data=json.dumps(requested, cls=DjangoJSONEncoder),
        actor_id=str(user.id),
        issue_id=str(issue.id),
        project_id=str(project.id),
        current_instance=current_instance,
        epoch=int(timezone.now().timestamp()),
        notification=True,
        origin=origin,
    )
    model_activity.delay(
        model_name="issue",
        model_id=str(issue.id),
        requested_data=requested,
        current_instance=current_instance,
        actor_id=user.id,
        slug=project.workspace.slug,
        origin=origin,
    )
    return changes


# --- Comments -----------------------------------------------------------------


def parse_comment(data):
    data = require_object(data)
    only_fields(data, ("text",))
    return text_field(data, "text", max_length=MAX_COMMENT, required=True)


def add_comment(request, user, issue, text):
    """Add a comment as the person, with the same activity and webhook as one written in the web app."""
    serializer = IssueCommentCreateSerializer(data={"comment_html": text_to_html(text)})
    if not serializer.is_valid():
        raise _validation_error(serializer)
    serializer.save(project_id=issue.project_id, issue_id=issue.id, actor=user)
    comment = IssueComment.objects.get(pk=serializer.instance.id)

    issue_activity.delay(
        type="comment.activity.created",
        requested_data=json.dumps(serializer.data, cls=DjangoJSONEncoder),
        actor_id=str(user.id),
        issue_id=str(issue.id),
        project_id=str(issue.project_id),
        current_instance=None,
        epoch=int(timezone.now().timestamp()),
    )
    model_activity.delay(
        model_name="issue_comment",
        model_id=str(comment.id),
        requested_data={"comment_html": comment.comment_html},
        current_instance=None,
        actor_id=user.id,
        slug=issue.workspace.slug,
        origin=base_host(request=request, is_app=True),
    )
    return IssueCommentSerializer(comment).data


# --- Time ---------------------------------------------------------------------


def parse_time_entry(data):
    data = require_object(data)
    only_fields(data, ("workspace", "work_item", "minutes", "date", "note"))
    minutes = data.get("minutes")
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 24 * 60:
        raise invalid_request("minutes must be a whole number from 1 to 1440.")
    return {
        "workspace": text_field(data, "workspace", max_length=255, required=True),
        "work_item": text_field(data, "work_item", max_length=100, required=True),
        "minutes": minutes,
        "date": date_field(data, "date"),
        "note": text_field(data, "note", max_length=MAX_NOTE),
    }


def add_time_entry(user, issue, *, minutes, day, note, zone, today):
    """Add hours the person worked on a work item on a given day.

    Today or up to `AGENT_MAX_BACKDATE_DAYS` back, never the future, and never into a month
    that has already been settled: those are figures somebody has read, and the way to
    change them is a person reopening the month.
    """
    if day > today:
        raise invalid_request("date must not be in the future.")
    if (today - day).days > conf.MAX_BACKDATE_DAYS:
        raise invalid_request(f"date may be at most {conf.MAX_BACKDATE_DAYS} days back.")

    # Noon, local: an entry written by hand has no start time, and noon keeps the day it is
    # filed under the same whichever way the clocks moved.
    logged_at = datetime.combine(day, time(12, 0), tzinfo=hr_timezone(zone))
    settled = settled_month_for(user.id, logged_at)
    if settled is not None:
        raise AgentError(
            "month_settled",
            "These hours fall in a month that has already been settled. A person has to reopen it in Plane first.",
            status_code=409,
            extra={"period_start": settled.period_start.isoformat()},
        )

    return IssueWorkLog.objects.create(
        issue=issue,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
        logged_by=user,
        duration=minutes * 60,
        started_at=None,
        logged_at=logged_at,
        description=note,
        created_by=user,
        updated_by=user,
    )
