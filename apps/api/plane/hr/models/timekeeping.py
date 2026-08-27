# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Hours that are not attached to a work item, and the daily attendance record.

Two separate things, deliberately. Attendance answers "when was this person at
work" and has a shape the law cares about — a start, an end and the breaks in
between. A time entry answers "what did those hours go on". Conflating them would
mean inventing a start time for every internal meeting.

Neither of these ever reaches the CRM. A work item timer does, because it hangs
off an issue; nothing in this module does.
"""

# Django imports
from django.db import models

# Module imports
from plane.hr.models.base import HrBaseModel


class HrTimeEntry(HrBaseModel):
    """Hours with no work item behind them: meetings, training, admin, travel.

    Also the landing place for every hour imported from a previous system. That is
    not a coincidence — it is the reason the table exists in this shape. Imported
    history written as work item timers would be pushed to the CRM by the existing
    mirror and would duplicate customer billing; written here it structurally
    cannot be.
    """

    class Category(models.IntegerChoices):
        MEETING = 10, "Internal meeting"
        TRAINING = 20, "Training"
        ADMIN = 30, "Administration"
        TRAVEL = 40, "Travel"
        ON_CALL = 50, "On call"
        CORRECTION = 60, "Correction"
        IMPORTED = 70, "Imported"

    class Source(models.IntegerChoices):
        MANUAL = 10, "Entered by hand"
        IMPORT = 20, "Imported"
        SYSTEM = 30, "Created by the system"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_time_entries",
    )
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    # A plain date rather than a timestamp. Everything this module owns natively
    # sidesteps the timezone question entirely by recording the day directly.
    entry_date = models.DateField()
    # Signed, so a correction can subtract without needing a separate mechanism.
    minutes = models.IntegerField()
    category = models.PositiveSmallIntegerField(choices=Category.choices, default=Category.ADMIN)
    source = models.PositiveSmallIntegerField(choices=Source.choices, default=Source.MANUAL)

    # Optional cost attribution, and deliberately not a cascade: if the project is
    # deleted later the hours survive with an empty project. A work item timer
    # cannot do this, because its project reference is required and cascading.
    project = models.ForeignKey(
        "db.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_time_entries",
    )
    import_batch = models.ForeignKey(
        "hr.HrImportBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="time_entries",
    )
    locked_period = models.ForeignKey(
        "hr.HrPeriod",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_time_entries",
    )
    note = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.profile_id} {self.entry_date} {self.minutes}m"

    class Meta:
        verbose_name = "HR Time Entry"
        verbose_name_plural = "HR Time Entries"
        db_table = "hr_time_entries"
        ordering = ("-entry_date",)
        constraints = [
            models.CheckConstraint(condition=~models.Q(minutes=0), name="hr_time_entry_nonzero"),
            models.CheckConstraint(
                condition=models.Q(minutes__gte=-1440) & models.Q(minutes__lte=1440),
                name="hr_time_entry_within_a_day",
            ),
        ]
        indexes = [
            models.Index(fields=["profile", "entry_date"]),
            models.Index(fields=["import_batch"]),
        ]


class HrAttendanceDay(HrBaseModel):
    """When somebody was at work on a given day, and for how long net of breaks.

    Times are stored as local wall clock plus the zone they were given in, not as
    instants. What is being recorded is the person's statement — "I started at
    eight" — and storing the instant and re-deriving eight o'clock on read would
    let a timezone database update rewrite the record. The elapsed duration is
    resolved once, at save, by subtracting instants, which is what makes the two
    clock-change days a year come out right.
    """

    class RecordingMethod(models.IntegerChoices):
        MANUAL = 10, "Entered by the person"
        CORRECTED = 20, "Corrected afterwards"
        IMPORTED = 30, "Imported"

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_attendance_days",
    )
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.CASCADE,
        related_name="attendance_days",
    )
    work_date = models.DateField()

    started_at_local = models.TimeField()
    ended_at_local = models.TimeField(null=True, blank=True)
    # Snapshotted so that moving somebody to another zone later does not silently
    # rewrite what their previous days meant.
    local_timezone = models.CharField(max_length=64)
    break_minutes = models.PositiveSmallIntegerField(default=0)
    crosses_midnight = models.BooleanField(default=False)

    # Materialised at save, never recomputed on read.
    net_minutes = models.IntegerField(default=0)

    recording_method = models.PositiveSmallIntegerField(
        choices=RecordingMethod.choices,
        default=RecordingMethod.MANUAL,
    )
    note = models.TextField(blank=True, default="")
    locked_period = models.ForeignKey(
        "hr.HrPeriod",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_attendance_days",
    )

    def __str__(self):
        return f"{self.profile_id} {self.work_date}"

    class Meta:
        verbose_name = "HR Attendance Day"
        verbose_name_plural = "HR Attendance Days"
        db_table = "hr_attendance_days"
        ordering = ("-work_date",)
        constraints = [
            # One row per person per day. Leaving and coming back is one row with a
            # longer break, not two rows; splitting into segments is a problem for
            # a company several times this size.
            models.UniqueConstraint(fields=["profile", "work_date"], name="unique_hr_attendance_per_day"),
            models.CheckConstraint(
                condition=models.Q(break_minutes__lte=480),
                name="hr_attendance_break_sane",
            ),
            models.CheckConstraint(
                condition=models.Q(net_minutes__gte=0) & models.Q(net_minutes__lte=1440),
                name="hr_attendance_net_within_a_day",
            ),
        ]
        indexes = [models.Index(fields=["profile", "work_date"])]
