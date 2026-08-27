# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who works here, under what arrangement, and what may be recorded about them.

The contract is versioned rather than edited in place because a change agreed in
April must not silently rewrite what March was measured against. Every figure the
module produces resolves the contract that was valid on the day in question.
"""

# Django imports
from django.db import models

# Module imports
from plane.hr.models.base import HrBaseModel


class HrEmploymentProfile(HrBaseModel):
    """One row per person per workspace: the anchor every other HR record hangs off.

    Kept separate from ``WorkspaceMember`` so that removing someone from the
    workspace does not take their employment history with it, and so that HR data
    is not readable through the ordinary member endpoints.
    """

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_employment_profiles",
    )
    member = models.ForeignKey(
        "db.User",
        on_delete=models.CASCADE,
        related_name="hr_employment_profiles",
    )
    # Empty means "use the workspace timezone". Set it only for someone whose
    # habitual place of work is elsewhere, because it decides which day — and so
    # which month — their hours land in.
    timezone = models.CharField(max_length=255, blank=True, default="")
    holiday_calendar = models.ForeignKey(
        "hr.HrHolidayCalendar",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profiles",
    )
    hire_date = models.DateField(null=True, blank=True)
    exit_date = models.DateField(null=True, blank=True)
    # Grants sight of everyone's HR data without making the person a workspace
    # admin. Deliberately a flag here rather than a fourth workspace role: the
    # role integer is shared with upstream and is not ours to extend.
    is_hr_manager = models.BooleanField(default=False)
    # Read-only for HR: personal hours stop being attributed once someone leaves,
    # but their closed periods stay readable.
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.member_id} in {self.workspace_id}"

    class Meta:
        verbose_name = "HR Employment Profile"
        verbose_name_plural = "HR Employment Profiles"
        db_table = "hr_employment_profiles"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "member"],
                name="unique_hr_profile_per_member",
            )
        ]


class HrContract(HrBaseModel):
    """A dated slice of someone's terms. Never edited retroactively — superseded.

    ``arrangement`` describes how the person actually works and is safe to set from
    day one. ``legal_form`` is the classification and stays unset until it has been
    confirmed externally. The three ``records_*`` switches are what the module acts
    on, and they are deliberately independent of both: what a system writes down
    about someone is a decision in its own right, and for anyone invoicing their own
    hours the safe default is to write down less, not more.
    """

    class Arrangement(models.TextChoices):
        REMOTE_FULL_TIME_INVOICING = "remote_full_time_invoicing", "Remote, full time, self-invoicing"
        REMOTE_PART_TIME_INVOICING = "remote_part_time_invoicing", "Remote, part time, self-invoicing"
        ONSITE_PART_TIME = "onsite_part_time", "On site, part time"
        ONSITE_FULL_TIME = "onsite_full_time", "On site, full time"

    class LegalForm(models.TextChoices):
        EMPLOYEE = "employee", "Employment relationship"
        FREE_SERVICE = "free_service", "Free service contract"
        CONTRACT_FOR_WORK = "contract_for_work", "Contract for work"

    class ShortfallHandling(models.TextChoices):
        # The module reports the shortfall and stops there. Anything else would be
        # an automated deduction, which is not something software should decide.
        REPORT_ONLY = "report_only", "Report only"
        MANUAL_DECISION = "manual_decision", "Report and require a recorded decision"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_contracts",
    )
    profile = models.ForeignKey(
        HrEmploymentProfile,
        on_delete=models.CASCADE,
        related_name="contracts",
    )
    valid_from = models.DateField()
    # Open-ended while the arrangement is current.
    valid_to = models.DateField(null=True, blank=True)

    arrangement = models.CharField(max_length=40, choices=Arrangement.choices)
    legal_form = models.CharField(max_length=30, choices=LegalForm.choices, blank=True, default="")

    # All three default to off. Turning one on is a deliberate act with a name
    # against it in the audit log.
    records_target_hours = models.BooleanField(default=False)
    records_attendance = models.BooleanField(default=False)
    records_leave_account = models.BooleanField(default=False)

    # Contracted weekly minutes. Note this is the collective-agreement week, which
    # is not necessarily 40 hours.
    weekly_minutes = models.PositiveIntegerField(null=True, blank=True)
    # Monthly volume agreed instead of a daily obligation. Used when
    # records_target_hours is off, so the person still has something to be measured
    # against without a per-day target being recorded for them.
    agreed_scope_minutes = models.PositiveIntegerField(null=True, blank=True)

    shortfall_handling = models.CharField(
        max_length=20,
        choices=ShortfallHandling.choices,
        default=ShortfallHandling.REPORT_ONLY,
    )
    note = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.profile_id} from {self.valid_from}"

    class Meta:
        verbose_name = "HR Contract"
        verbose_name_plural = "HR Contracts"
        db_table = "hr_contracts"
        ordering = ("-valid_from",)
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "valid_from"],
                name="unique_hr_contract_start_per_profile",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=models.F("valid_from")),
                name="hr_contract_valid_range",
            ),
        ]
        indexes = [models.Index(fields=["profile", "valid_from", "valid_to"])]
