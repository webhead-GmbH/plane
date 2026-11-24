# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Small builders for the company a connected app looks into: people, projects, work items, HR records."""

# Python imports
from datetime import date, datetime, timedelta, timezone as dt_timezone
from uuid import uuid4

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueComment,
    IssueWorkLog,
    Project,
    ProjectMember,
    State,
)
from plane.hr.models import (
    HrAbsence,
    HrAbsenceType,
    HrContract,
    HrEmploymentProfile,
    HrHoliday,
    HrHolidayCalendar,
    HrWorkSchedule,
)
from plane.tests.factories import UserFactory, WorkspaceFactory, WorkspaceMemberFactory

FULL = 480  # eight hours


def make_user(**fields):
    return UserFactory(username=uuid4().hex, **fields)


def make_workspace(owner=None, slug=None):
    owner = owner or make_user()
    workspace = WorkspaceFactory(owner=owner, **({"slug": slug} if slug else {}))
    WorkspaceMemberFactory(workspace=workspace, member=owner, role=ROLE.ADMIN.value)
    return workspace


def join(workspace, user, role=ROLE.MEMBER.value, is_active=True):
    return WorkspaceMemberFactory(workspace=workspace, member=user, role=role, is_active=is_active)


def make_project(workspace, identifier="PRJ", members=(), name=None, **fields):
    project = Project.objects.create(
        workspace=workspace, name=name or f"Project {identifier}", identifier=identifier, **fields
    )
    for user, role in members:
        ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=role)
    return project


def make_state(project, group="started", name=None):
    return State.objects.get_or_create(
        project=project,
        workspace=project.workspace,
        name=name or group.title(),
        group=group,
        defaults={"color": "#000000"},
    )[0]


def make_issue(project, name="A task", *, author=None, assignees=(), group="started", **fields):
    issue = Issue.objects.create(
        project=project, workspace=project.workspace, name=name, state=make_state(project, group), **fields
    )
    if author is not None:
        # BaseModel.save fills created_by from the request user, which is nobody here.
        Issue.objects.filter(pk=issue.pk).update(created_by=author)
        issue.created_by = author
    for person in assignees:
        IssueAssignee.objects.create(issue=issue, assignee=person, project=project, workspace=project.workspace)
    return issue


def comment(issue, text, actor=None):
    return IssueComment.objects.create(
        issue=issue, project=issue.project, workspace=issue.workspace, actor=actor, comment_html=text
    )


def log_time(issue, user, minutes, *, at, running=False):
    """Hours on a work item, ending at `at` (a timezone-aware moment)."""
    seconds = minutes * 60
    return IssueWorkLog.objects.create(
        issue=issue,
        project=issue.project,
        workspace=issue.workspace,
        logged_by=user,
        duration=None if running else seconds,
        started_at=at - timedelta(seconds=seconds),
        logged_at=at,
    )


def employ(workspace, user, *, tz="Europe/Vienna", schedule=True, days=(0, 1, 2, 3, 4), minutes=FULL):
    """Give a person an employment record, a contract and (usually) a Monday-to-Friday schedule."""
    profile = HrEmploymentProfile.objects.create(
        workspace=workspace, member=user, timezone=tz, hire_date=date(2020, 1, 1)
    )
    HrContract.objects.create(
        workspace=workspace,
        profile=profile,
        valid_from=date(2020, 1, 1),
        arrangement=HrContract.Arrangement.ONSITE_FULL_TIME,
        records_target_hours=True,
        records_leave_account=True,
        weekly_minutes=minutes * len(days),
    )
    if schedule:
        fields = {f"{name}_minutes": minutes if index in days else 0 for index, name in enumerate(_WEEKDAYS)}
        HrWorkSchedule.objects.create(workspace=workspace, profile=profile, valid_from=date(2020, 1, 1), **fields)
    return profile


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def add_holiday(workspace, day, name="Test Holiday", fraction=1):
    calendar = HrHolidayCalendar.objects.filter(is_default=True).first() or HrHolidayCalendar.objects.create(
        workspace=workspace, name="Test calendar", country_code="AT", is_default=True
    )
    return HrHoliday.objects.create(
        workspace=workspace, calendar=calendar, date=day, name_de=f"{name} (de)", name_en=name, day_fraction=fraction
    )


def absence_type(workspace, code="urlaub", name="Annual leave", **fields):
    return HrAbsenceType.objects.get_or_create(
        workspace=workspace,
        code=code,
        defaults={"name_de": name, "name_en": name, "consumes_leave_entitlement": code == "urlaub", **fields},
    )[0]


def absent(profile, first, last=None, *, kind=None, state=HrAbsence.State.APPROVED, reason="", **fields):
    kind = kind or absence_type(profile.workspace)
    return HrAbsence.objects.create(
        workspace=profile.workspace,
        profile=profile,
        absence_type=kind,
        start_date=first,
        end_date=last or first,
        state=state,
        reason=reason,
        **fields,
    )


def at(year, month, day, hour=12, minute=0):
    """A timezone-aware moment in UTC."""
    return datetime(year, month, day, hour, minute, tzinfo=dt_timezone.utc)
