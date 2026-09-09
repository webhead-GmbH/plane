# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The record of who changed what, and the batches that brought old data in.

Work item timers are editable by the person who logged them and by any project
administrator, and none of those edits leaves a trace anywhere. Once figures from
those timers are what somebody is paid against, that is not good enough, so
everything this module does to an hour is written down here.
"""

# Django imports
from django.db import models

# Module imports
from plane.hr.models.base import HrBaseModel


class HrAuditLog(models.Model):
    """Append-only. Written by the module, never updated, never deleted.

    Not built on the shared base class: this is the highest-volume table here and
    an ordered integer key is smaller and cheaper than a random one, and there is
    no such thing as updating a row so the authorship fields would be misleading.
    """

    id = models.BigAutoField(primary_key=True)
    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_audit_logs",
    )
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_audit_entries",
    )
    # Kept alongside the reference because the whole point of this table is to
    # still make sense after the account it points at is gone.
    actor_email = models.CharField(max_length=255, blank=True, default="")

    # The person the change was about, which is not always the person who made it.
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )

    object_type = models.CharField(max_length=64)
    object_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=48)
    changes = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True, default="")
    # Correlates an entry with the request that caused it.
    request_id = models.CharField(max_length=64, blank=True, default="")

    def __str__(self):
        return f"{self.occurred_at:%Y-%m-%d %H:%M} {self.action}"

    class Meta:
        verbose_name = "HR Audit Log"
        verbose_name_plural = "HR Audit Log"
        db_table = "hr_audit_logs"
        ordering = ("-occurred_at",)
        indexes = [
            models.Index(fields=["workspace", "-occurred_at"]),
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["profile", "-occurred_at"]),
        ]


class HrImportBatch(HrBaseModel):
    """One upload of historical data, reversible as a unit.

    Nothing is written until somebody has seen what would be written. The preview
    holds the parsed rows and a verdict on each, and only then does committing
    produce records — each stamped with this batch, so undoing it is exact. An undo
    is refused once any of those records has been counted into a closed month.
    """

    class Kind(models.IntegerChoices):
        TIME_ENTRIES = 10, "Hours"
        ABSENCES = 20, "Absences"
        OPENING_BALANCES = 30, "Opening balances"
        HOLIDAYS = 40, "Holidays"
        ATTENDANCE = 50, "Attendance"

    class State(models.IntegerChoices):
        UPLOADED = 10, "Uploaded"
        VALIDATING = 20, "Checking"
        PREVIEW_READY = 30, "Ready to review"
        COMMITTING = 40, "Writing"
        COMMITTED = 50, "Written"
        FAILED = 60, "Failed"
        ROLLED_BACK = 70, "Undone"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_import_batches",
    )
    initiated_by = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_import_batches",
    )
    kind = models.PositiveSmallIntegerField(choices=Kind.choices)
    state = models.PositiveSmallIntegerField(choices=State.choices, default=State.UPLOADED)

    filename = models.CharField(max_length=255, blank=True, default="")
    file_format = models.CharField(max_length=8, blank=True, default="")
    # The upload is kept, so what was actually handed over can always be re-read.
    source_asset = models.ForeignKey(
        "db.FileAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_import_sources",
    )
    # Guards against the same file being applied twice.
    checksum = models.CharField(max_length=64, blank=True, default="")

    row_count = models.PositiveIntegerField(default=0)
    valid_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    preview = models.JSONField(default=dict, blank=True)
    errors = models.JSONField(default=list, blank=True)

    committed_at = models.DateTimeField(null=True, blank=True)
    rolled_back_at = models.DateTimeField(null=True, blank=True)
    rolled_back_by = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_rolled_back_imports",
    )
    rollback_reason = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.get_kind_display()} {self.filename or self.id}"

    class Meta:
        verbose_name = "HR Import Batch"
        verbose_name_plural = "HR Import Batches"
        db_table = "hr_import_batches"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "kind", "checksum"],
                condition=models.Q(state=50) & ~models.Q(checksum=""),
                name="unique_hr_committed_import",
            )
        ]
        indexes = [models.Index(fields=["workspace", "state"])]
