# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The month, the per-day ledger it is built from, and the balances it starts at.

The ledger is the load-bearing idea here. There is one row per person per day,
holding the figures and the identifiers of the records that produced them, and it
is rebuilt from scratch on a schedule while the month is open. Closing the month
stops the rebuild touching those rows, so the same table that serves the live view
is the frozen record afterwards — one way to read a month, whatever its state.

Rebuilding rather than reading through to the source is not caution for its own
sake. Deleting a work item soft-deletes every timer on it, including other
people's, and those rows then vanish from the default manager with nothing written
down anywhere. A figure computed on the fly would quietly shrink. The ledger
instead notices that identifiers it saw last time are gone, says so, and asks a
human — because whether the hours were withdrawn on purpose or lost by accident is
not something the remaining data can answer.
"""

# Django imports
from django.contrib.postgres.fields import ArrayField
from django.db import models

# Module imports
from plane.hr.models.base import HrBaseModel


class HrPeriod(HrBaseModel):
    """One person, one month, and how far through closing it we are."""

    class State(models.IntegerChoices):
        OPEN = 10, "Open"
        SUBMITTED = 20, "Submitted"
        APPROVED = 30, "Approved"
        LOCKED = 40, "Locked"
        # A locked month that had to be corrected. It never returns to open: it is
        # re-locked, leaving both trails visible rather than pretending the first
        # close never happened.
        REOPENED = 50, "Reopened"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_periods",
    )
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.CASCADE,
        related_name="periods",
    )
    # Stored as dates rather than a year and a month, so a range query is one index
    # scan and a move to some other period length costs nothing.
    period_start = models.DateField()
    period_end = models.DateField()
    state = models.PositiveSmallIntegerField(choices=State.choices, default=State.OPEN)

    # All null while the month is open; all present once it is locked.
    target_minutes = models.IntegerField(null=True, blank=True)
    actual_minutes = models.IntegerField(null=True, blank=True)
    balance_minutes = models.IntegerField(null=True, blank=True)
    opening_balance_minutes = models.IntegerField(null=True, blank=True)
    closing_balance_minutes = models.IntegerField(null=True, blank=True)
    project_minutes = models.IntegerField(null=True, blank=True)
    non_project_minutes = models.IntegerField(null=True, blank=True)
    attendance_minutes = models.IntegerField(null=True, blank=True)
    absence_minutes = models.IntegerField(null=True, blank=True)
    holiday_minutes = models.IntegerField(null=True, blank=True)
    leave_consumed_minutes = models.IntegerField(null=True, blank=True)
    balance_consumed_minutes = models.IntegerField(null=True, blank=True)
    overtime_minutes = models.IntegerField(null=True, blank=True)

    # The inputs the figures were derived from — which contract, which schedule,
    # which calendar, which absences, the timezone used, the per-day target array.
    # Not the outputs; those are the columns above. This is what makes a closed
    # month explicable a year later.
    snapshot = models.JSONField(null=True, blank=True)
    computation_version = models.PositiveSmallIntegerField(default=1)

    submitted_by = models.ForeignKey(
        "db.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="hr_submitted_periods"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "db.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="hr_approved_periods"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        "db.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="hr_locked_periods"
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        "db.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="hr_reopened_periods"
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopen_reason = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.profile_id} {self.period_start:%Y-%m}"

    class Meta:
        verbose_name = "HR Period"
        verbose_name_plural = "HR Periods"
        db_table = "hr_periods"
        ordering = ("-period_start",)
        constraints = [
            models.UniqueConstraint(fields=["profile", "period_start"], name="unique_hr_period_per_profile"),
            models.CheckConstraint(
                condition=models.Q(period_end__gt=models.F("period_start")),
                name="hr_period_valid_range",
            ),
            # The database refuses to record a month as closed without the figures
            # it was closed on.
            models.CheckConstraint(
                condition=models.Q(state__lt=40)
                | (
                    models.Q(target_minutes__isnull=False)
                    & models.Q(actual_minutes__isnull=False)
                    & models.Q(balance_minutes__isnull=False)
                ),
                name="hr_period_locked_requires_figures",
            ),
        ]
        indexes = [models.Index(fields=["workspace", "period_start", "state"])]


class HrPeriodDay(HrBaseModel):
    """One person, one day: the figures and what produced them."""

    class DayKind(models.IntegerChoices):
        WORKDAY = 10, "Working day"
        NON_WORKING = 20, "Not a working day"
        HOLIDAY = 30, "Public holiday"
        HALF_HOLIDAY = 40, "Half holiday"
        ABSENCE = 50, "Absent"
        PARTIAL_ABSENCE = 60, "Partly absent"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_period_days",
    )
    period = models.ForeignKey(HrPeriod, on_delete=models.CASCADE, related_name="days")
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.CASCADE,
        related_name="period_days",
    )
    work_date = models.DateField()

    target_minutes = models.IntegerField(default=0)
    project_minutes = models.IntegerField(default=0)
    non_project_minutes = models.IntegerField(default=0)
    attendance_minutes = models.IntegerField(null=True, blank=True)
    absence_minutes = models.IntegerField(default=0)
    holiday_minutes = models.IntegerField(default=0)
    actual_minutes = models.IntegerField(default=0)
    balance_minutes = models.IntegerField(default=0)
    # The share of the day's absence that came out of the annual leave account,
    # and the share that came out of accumulated time. Kept apart because they are
    # different accounts with different rules, and because a day can draw on
    # neither — sick leave is credited but paid for from neither balance.
    leave_minutes = models.IntegerField(default=0)
    balance_consumed_minutes = models.IntegerField(default=0)
    day_kind = models.PositiveSmallIntegerField(choices=DayKind.choices, default=DayKind.WORKDAY)

    # What the figures were built from. Kept so a closed month can still show which
    # entries it counted after those entries are gone, and so the next rebuild can
    # tell that something it counted last time has disappeared.
    worklog_ids = ArrayField(models.UUIDField(), default=list, blank=True)
    time_entry_ids = ArrayField(models.UUIDField(), default=list, blank=True)

    last_rebuilt_at = models.DateTimeField(null=True, blank=True)
    # Raised when a rebuild finds that something it previously counted is no longer
    # there. A person decides what that means; the module only notices.
    needs_review = models.BooleanField(default=False)
    note = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.profile_id} {self.work_date}"

    class Meta:
        verbose_name = "HR Period Day"
        verbose_name_plural = "HR Period Days"
        db_table = "hr_period_days"
        ordering = ("work_date",)
        constraints = [
            models.UniqueConstraint(fields=["period", "work_date"], name="unique_hr_period_day"),
        ]
        indexes = [
            models.Index(fields=["profile", "work_date"]),
            models.Index(fields=["period", "work_date"]),
        ]


class HrOpeningBalance(HrBaseModel):
    """What somebody's balance was on the day the module started counting.

    These are agreed rather than derived, so the record keeps how confident anyone
    is in the number and what it was based on. Corrections are new rows pointing at
    the row they replace; nothing here is edited, because a balance that quietly
    changed is a balance nobody can argue about afterwards.
    """

    class Kind(models.IntegerChoices):
        TIME_BALANCE = 10, "Time balance"
        LEAVE = 20, "Leave"
        OVERTIME_BANK = 30, "Overtime to be paid"

    class Confidence(models.IntegerChoices):
        EXACT = 10, "Taken from records"
        RECONSTRUCTED = 20, "Reconstructed"
        ESTIMATED = 30, "Estimated"
        AGREED = 40, "Agreed with the person"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_opening_balances",
    )
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.CASCADE,
        related_name="opening_balances",
    )
    effective_on = models.DateField()
    kind = models.PositiveSmallIntegerField(choices=Kind.choices)
    minutes = models.IntegerField()
    confidence = models.PositiveSmallIntegerField(choices=Confidence.choices, default=Confidence.AGREED)
    basis = models.TextField()

    source_document_asset = models.ForeignKey(
        "db.FileAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_opening_balance_documents",
    )
    import_batch = models.ForeignKey(
        "hr.HrImportBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opening_balances",
    )
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supersedes",
    )

    # Nothing is counted from a balance the person has not seen.
    acknowledged_by = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_acknowledged_balances",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.profile_id} {self.get_kind_display()} {self.effective_on}"

    class Meta:
        verbose_name = "HR Opening Balance"
        verbose_name_plural = "HR Opening Balances"
        db_table = "hr_opening_balances"
        ordering = ("-effective_on",)
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "kind", "effective_on"],
                condition=models.Q(superseded_by__isnull=True),
                name="unique_hr_current_opening_balance",
            )
        ]
        indexes = [models.Index(fields=["profile", "kind", "effective_on"])]
