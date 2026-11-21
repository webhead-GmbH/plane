# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Which work items a connected person may see, and how they are described to an app.

Visibility is not re-invented here. It is the rule the rest of Plane already applies
(`visible_issue_q`): an active member of the project sees everything in it, except
that a guest sees only what they created unless the project lets guests see more.
On top of that, drafts, archived items, items in archived projects and work awaiting
triage are left out, as in the web app's own lists, and so is anything in a
workspace the person has since left.

Everything is decided at query time. Taking someone out of a project takes effect on
that app's very next call, because there is nothing remembered to go stale.
"""

# Python imports
import hashlib
import html
import re
from uuid import UUID

# Django imports
from django.conf import settings
from django.db.models import Exists, F, OuterRef, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.html import strip_tags

# Module imports
from plane.api.views.issue import visible_issue_q
from plane.agent.errors import invalid_request
from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueWorkLog,
    Project,
    ProjectMember,
    WorkspaceMember,
)
from plane.app.permissions import ROLE
from plane.hr.services.computation import minutes_from_seconds

# Longest stretch of text from a work item or comment handed over in one piece.
MAX_TEXT = 20000


def description_version(html_text):
    """A short fingerprint of a description as it is stored.

    It is what an app sends back to say "I edited the description I read", so that an edit made
    on top of somebody else's later change is refused instead of silently replacing it.
    """
    return hashlib.sha256((html_text or "").encode("utf-8")).hexdigest()[:16]


def visible_issues(user):
    """The work items this person can see, as a queryset to narrow further."""
    can_view = Issue.issue_objects.filter(id=OuterRef("id")).filter(visible_issue_q(user)).values("id")
    still_in_workspace = WorkspaceMember.objects.filter(
        workspace_id=OuterRef("workspace_id"), member=user, is_active=True
    )
    return Issue.issue_objects.filter(Exists(can_view), Exists(still_in_workspace))


def visible_projects(user):
    """Projects the person is an active member of, in workspaces they still belong to."""
    member_of = ProjectMember.objects.filter(project_id=OuterRef("id"), member=user, is_active=True)
    still_in_workspace = WorkspaceMember.objects.filter(
        workspace_id=OuterRef("workspace_id"), member=user, is_active=True
    )
    return Project.objects.filter(archived_at__isnull=True).filter(Exists(member_of), Exists(still_in_workspace))


def listed_projects(user):
    """The projects the person is shown in a list: their own, and, as in the web app, every project of a
    workspace they administer.

    Being listed is not being able to act. In a project the person is not a member of, the web app lets
    a workspace admin see that it exists and nothing more, and so does this: its work items, members,
    states and labels stay out of reach and creating work there is refused until they join.
    """
    administers = WorkspaceMember.objects.filter(
        workspace_id=OuterRef("workspace_id"), member=user, is_active=True, role=ROLE.ADMIN.value
    )
    return Project.objects.filter(archived_at__isnull=True).filter(
        Q(pk__in=visible_projects(user).values("pk")) | Q(Exists(administers))
    )


def with_my_time(queryset, user):
    """Annotate each work item with the seconds this person has logged on it."""
    mine = (
        IssueWorkLog.objects.filter(issue_id=OuterRef("id"), logged_by=user, duration__isnull=False)
        .order_by()
        .values("issue_id")
        .annotate(total=Sum("duration"))
        .values("total")
    )
    return queryset.annotate(my_logged_seconds=Coalesce(mine, Value(0)))


def reference(issue):
    """The short name people use for a work item: the project's identifier and its number."""
    return f"{issue.project.identifier}-{issue.sequence_id}"


def web_url(issue):
    base = (getattr(settings, "WEB_URL", None) or getattr(settings, "APP_BASE_URL", None) or "").rstrip("/")
    return f"{base}/{issue.workspace.slug}/browse/{reference(issue)}/" if base else None


_DROPPED_ELEMENTS = re.compile(r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_LINE_BREAKS = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_BLOCK_ENDS = re.compile(r"<\s*/\s*(p|div|h[1-6]|li|tr|blockquote|pre|ul|ol)\s*>", re.IGNORECASE)
_LIST_ITEM = re.compile(r"<\s*li\b[^>]*>", re.IGNORECASE)


def plain_text(value, limit=MAX_TEXT):
    """Markup removed, paragraphs kept apart and whitespace tidied, for text a program will read.

    Scripts and styles are dropped with their contents. Paragraph and list structure is
    kept as line breaks, because a description whose paragraphs run together reads as
    one confused sentence. What comes back is still somebody else's words: it is the
    app's job not to treat it as an instruction to anyone.
    """
    if not value:
        return ""
    text = _DROPPED_ELEMENTS.sub("", str(value))
    text = _LIST_ITEM.sub("- ", _LINE_BREAKS.sub("\n", text))
    text = _BLOCK_ENDS.sub("\n", text)
    text = html.unescape(strip_tags(text))
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


def compact(issue):
    """A work item as a list shows it. Needs `project`, `workspace`, `state` and the prefetches below."""
    return {
        "id": str(issue.id),
        "ref": reference(issue),
        "url": web_url(issue),
        "name": issue.name,
        "workspace": issue.workspace.slug,
        "project": {
            "id": str(issue.project_id),
            "name": issue.project.name,
            "identifier": issue.project.identifier,
        },
        "state": (
            {"id": str(issue.state_id), "name": issue.state.name, "group": issue.state.group} if issue.state else None
        ),
        "priority": issue.priority,
        "start_date": issue.start_date.isoformat() if issue.start_date else None,
        "target_date": issue.target_date.isoformat() if issue.target_date else None,
        "estimate": issue.estimate_point.value if issue.estimate_point_id else None,
        "assignees": [{"id": str(person.id), "display_name": person.display_name} for person in assignees_of(issue)],
        "labels": [label.name for label in labels_of(issue)],
        "parent": str(issue.parent_id) if issue.parent_id else None,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
        "completed_at": issue.completed_at.isoformat() if issue.completed_at else None,
        "my_logged_minutes": minutes_from_seconds(getattr(issue, "my_logged_seconds", 0) or 0),
    }


def with_relations(queryset):
    """Everything `compact` reads, fetched together.

    The people and labels come through their link rows, not through the many-to-many
    shortcut: that shortcut also returns links that were deleted (somebody taken off a work
    item still appears on it), and a person who has since left the project is not an
    assignee any more, whatever the old link says. Same rule the web app's own lists apply.
    """
    return queryset.select_related("project", "workspace", "state", "estimate_point").prefetch_related(
        Prefetch(
            "issue_assignee",
            queryset=IssueAssignee.objects.filter(
                assignee__member_project__is_active=True,
                assignee__member_project__project_id=F("project_id"),
            ).select_related("assignee"),
        ),
        Prefetch("label_issue", queryset=IssueLabel.objects.select_related("label")),
    )


def assignees_of(issue):
    """The people on a work item, once each. Needs `with_relations`."""
    seen = {}
    for link in issue.issue_assignee.all():
        seen.setdefault(link.assignee_id, link.assignee)
    return list(seen.values())


def labels_of(issue):
    seen = {}
    for link in issue.label_issue.all():
        seen.setdefault(link.label_id, link.label)
    return list(seen.values())


MAX_COMMENTS = 30


def parse_uuid(raw, name):
    try:
        return UUID(raw)
    except (TypeError, ValueError, AttributeError):
        raise invalid_request(f"{name} must be an id.")


def resolve(user, slug, ref):
    """The work item a short reference (`WEB-1`, any case) or an id names, if the person can see it.

    An id is tried first: the tail of a UUID can be all digits, and must not be mistaken for
    the number of a work item.
    """
    items = visible_issues(user).filter(workspace__slug=slug)
    try:
        items = items.filter(id=UUID(ref))
    except (TypeError, ValueError, AttributeError):
        project_identifier, _, number = (ref or "").rpartition("-")
        if not (project_identifier and number.isdigit()):
            raise invalid_request("ref must be a work item reference such as WEB-12, or its id.")
        items = items.filter(project__identifier__iexact=project_identifier, sequence_id=int(number))
    return with_relations(with_my_time(items, user)).first()


def detail(issue):
    """A work item with its description and recent comments, as plain text."""
    comments = IssueComment.objects.filter(issue=issue).select_related("actor").order_by("-created_at")[:MAX_COMMENTS]
    payload = compact(issue)
    payload["description"] = plain_text(issue.description_html or issue.description_stripped)
    payload["description_version"] = description_version(issue.description_html)
    payload["comments"] = [
        {
            "id": str(comment.id),
            "author": comment.actor.display_name if comment.actor_id else None,
            "created_at": comment.created_at.isoformat(),
            "text": plain_text(comment.comment_html or comment.comment_stripped, 5000),
        }
        for comment in reversed(list(comments))
    ]
    return payload
