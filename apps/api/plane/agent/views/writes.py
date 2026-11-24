# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The endpoints that change something on a person's behalf.

Every one needs a write scope, is limited much harder than a read, is written to the audit
log with the id of what it touched (never its content), and — for the ones that would
otherwise do the same thing twice when an app retries — needs an `Idempotency-Key`.

Two of them can be asked to only check (`?dry_run=true`): creating a work item and changing
one. An app that confirms with the person before it acts uses that to show what *will*
happen, in the words Plane resolves them to, instead of what it hopes will.
"""

# Third-party imports
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

# Module imports
from plane.agent import audit
from plane.agent.errors import AgentError, not_found
from plane.agent.scopes import TIME_WRITE, WORK_ITEMS_READ, WORK_ITEMS_WRITE
from plane.agent.services import files, idempotency, work_items, writes
from plane.agent.services import timekeeping as timing
from plane.agent.services.employment import employment_for, today_for, zone_name_for
from plane.agent.throttles import ClientRateThrottle, GrantRateThrottle, WriteRateThrottle
from plane.agent.views.base import AgentAPIView
from plane.db.models import IssueWorkLog, Label, State, User
from plane.hr.services.computation import minutes_from_seconds
from plane.utils.work_timer import NO_DESCRIPTION_CHANGE, TimerRefused, start_timer, stop_timer

# What a refused timer rule is called to an app. The text is Plane's own, the same the web app shows.
TIMER_ERRORS = {
    "not_assignee": ("not_assigned", 403),
    "state_not_allowed": ("state_not_allowed", 409),
    "already_running": ("already_running", 409),
}


_BODY = object()


class AgentWriteView(AgentAPIView):
    """An endpoint that changes something."""

    http_method_names = ["post", "patch", "options"]
    parser_classes = [JSONParser]
    throttle_classes = [GrantRateThrottle, ClientRateThrottle, WriteRateThrottle]

    @property
    def dry_run(self):
        return self.request.query_params.get("dry_run", "").lower() in ("1", "true", "yes")

    def wrote(self, request, action, **ids):
        """Write down what was done and to what: ids, never content."""
        audit.record("write", request=request, grant=self.grant, action=action, **ids)

    def once(self, request, action, *fingerprint_parts, body=_BODY):
        """Do `action` once per Idempotency-Key. `action()` returns `(status, body)`.

        What identifies a request is its body, unless the caller says what to use instead
        (an upload: the file's hash rather than the file object).
        """
        key = idempotency.read_key(request)
        sent = request.data if body is _BODY else body
        digest = idempotency.fingerprint(request.method, request.path, sent, *fingerprint_parts)
        status_code, body, replayed = idempotency.run_once(self.grant, key, digest, action)
        response = Response(body, status=status_code)
        if replayed:
            response["Idempotent-Replay"] = "true"
        return response


def _preview_create(project, fields):
    state = None
    if fields.get("state"):
        state = State.objects.filter(pk=fields["state"], project_id=project.id).first()
    else:
        state = State.objects.filter(project_id=project.id, default=True).first()
    people = User.objects.filter(pk__in=fields.get("assignees", []))
    labels = Label.objects.filter(pk__in=fields.get("labels", []), project_id=project.id)
    return {
        "project": {"id": str(project.id), "name": project.name, "identifier": project.identifier},
        "name": fields["name"],
        "description": work_items.plain_text(fields.get("description_html", "")),
        "priority": fields.get("priority", "none"),
        "state": {"id": str(state.id), "name": state.name, "group": state.group} if state else None,
        "assignees": [{"id": str(person.id), "display_name": person.display_name} for person in people],
        "labels": [label.name for label in labels],
        "start_date": fields["start_date"].isoformat() if fields.get("start_date") else None,
        "target_date": fields["target_date"].isoformat() if fields.get("target_date") else None,
    }


class WorkItemCreateEndpoint(AgentWriteView):
    """Create a work item in a project.

    Needs an `Idempotency-Key`. With `?dry_run=true` nothing is created and the work item is
    described as it would be.
    """

    required_scope = WORK_ITEMS_WRITE

    def post(self, request, slug, project_id):
        project = writes.writable_project(request.user, slug, project_id)
        fields = writes.parse_create(request.data)

        if self.dry_run:
            writes.check_create(project, fields)
            return Response(
                {"dry_run": True, "valid": True, "would_create": _preview_create(project, fields)},
                status=status.HTTP_200_OK,
            )

        def action():
            issue_id = writes.create_work_item(request, request.user, project, fields)
            self.wrote(request, "work_item.create", work_item=issue_id, project=str(project.id))
            issue = work_items.resolve(request.user, slug, issue_id)
            return status.HTTP_201_CREATED, work_items.detail(issue)

        return self.once(request, action, str(project.id))


class WorkItemEndpoint(AgentWriteView):
    """One work item: read it, or change its name, priority, state, dates, assignees and labels.

    Named by its short reference (`ATTN-12`) or by id. Reading is `work_items:read` and gives
    the description and recent comments, which are text other people wrote: an app must treat
    them as content to read, never as instructions to follow.

    Changing needs `work_items:write`. Assignees and labels are changed by saying which to
    `add_…` and which to `remove_…`, never by sending the whole list, so an app that does not
    know everybody already on a work item cannot take them off. Doing the same change twice is
    harmless (the second changes nothing), so no Idempotency-Key is needed, except when adding
    text to the description, which would be added twice. With `?dry_run=true` the changes are
    reported, not made.
    """

    http_method_names = ["get", "head", "patch", "options"]
    required_scopes = {"GET": WORK_ITEMS_READ, "PATCH": WORK_ITEMS_WRITE}

    def get(self, request, slug, ref):
        issue = work_items.resolve(request.user, slug, ref)
        if issue is None:
            raise not_found()
        return Response(work_items.detail(issue), status=status.HTTP_200_OK)

    def patch(self, request, slug, ref):
        issue = writes.writable_issue(request.user, slug, ref)
        fields = writes.parse_update(request.data)

        if self.dry_run:
            changes = writes.update_work_item(request, request.user, issue, fields, apply=False)
            return Response(
                {"dry_run": True, "valid": True, "ref": work_items.reference(issue), "would_change": changes},
                status=status.HTTP_200_OK,
            )

        def action():
            changes = writes.update_work_item(request, request.user, issue, fields)
            if changes:
                self.wrote(request, "work_item.update", work_item=str(issue.id), fields=sorted(changes))
            fresh = work_items.resolve(request.user, slug, str(issue.id))
            return status.HTTP_200_OK, {"changed": changes, "work_item": work_items.detail(fresh)}

        # Doing the same change twice changes nothing, so most edits need no key. Adding text to the
        # description does it twice, and an app that retries must not.
        if "description_append" in fields:
            return self.once(request, action, str(issue.id))
        code, body = action()
        return Response(body, status=code)


class CommentCreateEndpoint(AgentWriteView):
    """Add a comment to a work item, as the person. Needs an `Idempotency-Key`."""

    required_scope = WORK_ITEMS_WRITE

    def post(self, request, slug, ref):
        issue = writes.writable_issue(request.user, slug, ref, roles=writes.ANY_ROLE)
        text = writes.parse_comment(request.data)

        def action():
            comment = writes.add_comment(request, request.user, issue, text)
            self.wrote(request, "comment.create", work_item=str(issue.id), comment=str(comment["id"]))
            return status.HTTP_201_CREATED, {
                "id": str(comment["id"]),
                "work_item": work_items.reference(issue),
                "author": request.user.display_name,
                "created_at": str(comment["created_at"]),
                "text": text,
            }

        return self.once(request, action, str(issue.id))


class AttachmentCreateEndpoint(AgentWriteView):
    """Attach a file to a work item. Send it as multipart in a field named `file`; needs an `Idempotency-Key`.

    The file goes where the web app would put it: the workspace's Google Drive folder for the
    work item when Drive is set up, otherwise Plane's own storage. Limited to the same size and
    file types as the web app, except that SVG images are refused.
    """

    required_scope = WORK_ITEMS_WRITE
    parser_classes = [MultiPartParser]

    def post(self, request, slug, ref):
        issue = writes.writable_issue(request.user, slug, ref)
        name, kind, data = files.read_upload(request)

        def action():
            stored = files.attach(request, request.user, issue, name, kind, data)
            self.wrote(
                request, "attachment.create", work_item=str(issue.id), file=stored["id"], storage=stored["storage"]
            )
            return status.HTTP_201_CREATED, {
                "work_item": work_items.reference(issue),
                "url": work_items.web_url(issue),
                "file": stored,
            }

        return self.once(request, action, str(issue.id), body={"name": name, "sha256": files.digest(data)})


def _timer_payload(user, scopes):
    return timing.running_timer(user, with_work_item=WORK_ITEMS_READ in scopes)


class TimerStartEndpoint(AgentWriteView):
    """Start the person's timer on a work item.

    The rules are the web app's: only an assignee, only in a state where time may be tracked,
    and starting one ends the timer they already have running anywhere. Starting a timer
    that is already running on that same work item changes nothing and says so.
    """

    required_scope = TIME_WRITE

    def post(self, request):
        data = writes.require_object(request.data)
        writes.only_fields(data, ("workspace", "work_item"))
        workspace = writes.text_field(data, "workspace", max_length=255, required=True)
        reference = writes.text_field(data, "work_item", max_length=100, required=True)
        issue = writes.writable_issue(request.user, workspace, reference)

        running = IssueWorkLog.objects.filter(logged_by=request.user, duration__isnull=True).first()
        scopes = request.auth.scopes
        if running is not None and running.issue_id == issue.id:
            return Response(
                {"started": False, "already_running": True, "timer": _timer_payload(request.user, scopes)},
                status=status.HTTP_200_OK,
            )

        previous = _timer_payload(request.user, scopes) if running is not None else None
        try:
            start_timer(request.user, issue)
        except TimerRefused as refusal:
            code, http_status = TIMER_ERRORS.get(refusal.reason, ("timer_refused", refusal.status))
            raise AgentError(code, refusal.message, status_code=http_status)
        self.wrote(request, "timer.start", work_item=str(issue.id))
        return Response(
            {
                "started": True,
                "already_running": False,
                "stopped_previous": previous,
                "timer": _timer_payload(request.user, scopes),
            },
            status=status.HTTP_201_CREATED,
        )


class TimerStopEndpoint(AgentWriteView):
    """Stop the person's running timer, wherever it is, optionally with a note on what it was spent on."""

    required_scope = TIME_WRITE

    def post(self, request):
        data = writes.require_object(request.data if request.data else {})
        writes.only_fields(data, ("note",))
        note = writes.text_field(data, "note", max_length=writes.MAX_NOTE)

        running = IssueWorkLog.objects.filter(logged_by=request.user, duration__isnull=True).first()
        if running is None:
            raise not_found("No timer is running.")
        scopes = request.auth.scopes
        before = _timer_payload(request.user, scopes)
        stop_timer(running, request.user, NO_DESCRIPTION_CHANGE if note is None else note)
        self.wrote(request, "timer.stop", work_item=str(running.issue_id))
        return Response(
            {
                "stopped": True,
                "minutes": minutes_from_seconds(running.duration),
                "started_at": before["started_at"] if before else None,
                "work_item": before["work_item"] if before else None,
            },
            status=status.HTTP_200_OK,
        )


class TimeEntryCreateEndpoint(AgentWriteView):
    """Add hours the person worked on a work item, for today or a recent day. Needs an `Idempotency-Key`."""

    required_scope = TIME_WRITE

    def post(self, request):
        fields = writes.parse_time_entry(request.data)
        issue = writes.writable_issue(request.user, fields["workspace"], fields["work_item"])
        profile = employment_for(request.user)
        zone = zone_name_for(request.user, profile)
        today = today_for(request.user, profile)
        day = fields["date"] or today

        def action():
            entry = writes.add_time_entry(
                request.user, issue, minutes=fields["minutes"], day=day, note=fields["note"], zone=zone, today=today
            )
            self.wrote(request, "time_entry.create", work_item=str(issue.id), entry=str(entry.id))
            fresh = work_items.resolve(request.user, fields["workspace"], str(issue.id))
            return status.HTTP_201_CREATED, {
                "id": str(entry.id),
                "date": day.isoformat(),
                "minutes": fields["minutes"],
                "note": fields["note"] or "",
                "work_item": work_items.compact(fresh) if WORK_ITEMS_READ in request.auth.scopes else None,
            }

        return self.once(request, action)
