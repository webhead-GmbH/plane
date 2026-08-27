# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Time away from work, and the entitlement it is drawn from.

Absence types carry four independent flags rather than one kind enum, because the
combinations are genuinely orthogonal: paid leave credits hours and draws down
entitlement, time off in lieu credits hours and draws down the balance, sick leave
credits hours and draws down neither, unpaid leave credits nothing.
"""

# Django imports
from django.db import models

# Module imports
from plane.hr.models.base import HrBaseModel


class HrAbsenceType(HrBaseModel):
    """A reason for being away, and what that reason does to the arithmetic."""

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_absence_types",
    )
    code = models.CharField(max_length=32)
    name_de = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True, default="")

    # Adds its minutes to the actual figure — true for paid leave, sick leave and
    # paid training, false for unpaid leave.
    credits_actual = models.BooleanField(default=True)
    # Draws down the annual leave entitlement. Annual leave only.
    consumes_leave_entitlement = models.BooleanField(default=False)
    # Draws down the accumulated time balance. Time off in lieu only.
    consumes_balance = models.BooleanField(default=False)
    # Payroll flag with no effect on the time arithmetic.
    is_paid = models.BooleanField(default=True)

    requires_approval = models.BooleanField(default=True)
    # A medical certificate, held separately and with tighter access than the
    # absence record itself.
    requires_document = models.BooleanField(default=False)
    max_consecutive_days = models.PositiveSmallIntegerField(null=True, blank=True)
    colour = models.CharField(max_length=9, blank=True, default="")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.workspace_id})"

    class Meta:
        verbose_name = "HR Absence Type"
        verbose_name_plural = "HR Absence Types"
        db_table = "hr_absence_types"
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(fields=["workspace", "code"], name="unique_hr_absence_type_code")
        ]


class HrAbsence(HrBaseModel):
    """One stretch of time away, resolved to minutes when it is saved."""

    class Granularity(models.IntegerChoices):
        FULL_DAY = 10, "Full day"
        HALF_DAY = 20, "Half day"
        HOURS = 30, "Hours"

    class Half(models.IntegerChoices):
        MORNING = 10, "Morning"
        AFTERNOON = 20, "Afternoon"

    class State(models.IntegerChoices):
        DRAFT = 10, "Draft"
        REQUESTED = 20, "Requested"
        APPROVED = 30, "Approved"
        REJECTED = 40, "Rejected"
        CANCELLED = 50, "Cancelled"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_absences",
    )
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.CASCADE,
        related_name="absences",
    )
    # PROTECT so a historical absence never loses its meaning.
    absence_type = models.ForeignKey(
        HrAbsenceType,
        on_delete=models.PROTECT,
        related_name="absences",
    )

    start_date = models.DateField()
    end_date = models.DateField()
    granularity = models.PositiveSmallIntegerField(
        choices=Granularity.choices,
        default=Granularity.FULL_DAY,
    )
    # Half days apply only at the ends of a range. A half day in the middle of a
    # week is its own record, which matches how people actually take them.
    start_half = models.PositiveSmallIntegerField(choices=Half.choices, null=True, blank=True)
    end_half = models.PositiveSmallIntegerField(choices=Half.choices, null=True, blank=True)
    minutes_per_day = models.PositiveIntegerField(null=True, blank=True)

    # Resolved against the schedule in force when the absence was recorded, and
    # then left alone. Recomputing a past absence against a schedule agreed years
    # later gives a different answer to the one the person was granted.
    total_minutes = models.PositiveIntegerField(default=0)

    state = models.PositiveSmallIntegerField(choices=State.choices, default=State.DRAFT)
    approved_by = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_approved_absences",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    rejection_reason = models.TextField(blank=True, default="")

    document_asset = models.ForeignKey(
        "db.FileAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_absence_documents",
    )
    # Set once the month containing this absence is closed, after which it can no
    # longer be edited or removed.
    locked_period = models.ForeignKey(
        "hr.HrPeriod",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_absences",
    )

    def __str__(self):
        return f"{self.profile_id} {self.start_date}..{self.end_date}"

    class Meta:
        verbose_name = "HR Absence"
        verbose_name_plural = "HR Absences"
        db_table = "hr_absences"
        ordering = ("-start_date",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="hr_absence_valid_range",
            ),
            models.CheckConstraint(
                condition=~models.Q(granularity=30) | models.Q(minutes_per_day__isnull=False),
                name="hr_absence_hours_need_minutes",
            ),
        ]
        indexes = [
            models.Index(fields=["profile", "start_date", "end_date"]),
            models.Index(fields=["workspace", "state", "start_date"]),
        ]


class HrLeaveEntitlement(HrBaseModel):
    """Annual leave for one leave year, counted in minutes.

    Minutes rather than days because a day is not a fixed quantity for anyone
    working uneven hours, and the moment contracted hours change mid-year the day
    figure becomes ambiguous while the minute figure does not. Days are computed
    for display from the schedule in force at the time of display, and never stored.

    The leave year runs from the anniversary of joining rather than from January,
    which is the statutory default here. Both ends are stored so that moving to a
    calendar-year basis later is a data change rather than a schema change.
    """

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_leave_entitlements",
    )
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.CASCADE,
        related_name="leave_entitlements",
    )
    leave_year_start = models.DateField()
    leave_year_end = models.DateField()

    entitlement_minutes = models.IntegerField(default=0)
    # Signed: leave can be carried forward, and it can also be taken in advance.
    carryover_minutes = models.IntegerField(default=0)
    adjustment_minutes = models.IntegerField(default=0)
    expires_on = models.DateField(null=True, blank=True)

    basis_note = models.TextField(blank=True, default="")
    # Set once the figure has been agreed with the person, after which it is not
    # edited — a change becomes a new adjustment with its own reason.
    is_final = models.BooleanField(default=False)

    @property
    def granted_minutes(self):
        return self.entitlement_minutes + self.carryover_minutes + self.adjustment_minutes

    def __str__(self):
        return f"{self.profile_id} {self.leave_year_start}"

    class Meta:
        verbose_name = "HR Leave Entitlement"
        verbose_name_plural = "HR Leave Entitlements"
        db_table = "hr_leave_entitlements"
        ordering = ("-leave_year_start",)
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "leave_year_start"],
                name="unique_hr_leave_year_per_profile",
            ),
            models.CheckConstraint(
                condition=models.Q(leave_year_end__gt=models.F("leave_year_start")),
                name="hr_leave_year_valid_range",
            ),
        ]
