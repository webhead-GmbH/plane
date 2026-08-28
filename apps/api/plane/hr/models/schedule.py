# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""What a person is expected to work, and which days are not working days.

Schedules are dated slices like contracts, and for the same reason, but they are
a separate record because they change more often — somebody moves their free day
without renegotiating anything.
"""

# Django imports
from django.db import models

# Module imports
from plane.hr.models.base import HrBaseModel

MAX_MINUTES_PER_DAY = 1440


class HrWorkSchedule(HrBaseModel):
    """Expected minutes per weekday, either company-wide or for one person.

    The seven weekdays are seven columns rather than a JSON array because the
    target for a day is looked up on every row of every report; a JSON blob turns
    each of those lookups into a Python loop over data the database could have
    filtered.
    """

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_work_schedules",
    )
    # Null means this is the workspace default, used by anyone without their own.
    profile = models.ForeignKey(
        "hr.HrEmploymentProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="work_schedules",
    )
    name = models.CharField(max_length=120, blank=True, default="")
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    monday_minutes = models.PositiveSmallIntegerField(default=0)
    tuesday_minutes = models.PositiveSmallIntegerField(default=0)
    wednesday_minutes = models.PositiveSmallIntegerField(default=0)
    thursday_minutes = models.PositiveSmallIntegerField(default=0)
    friday_minutes = models.PositiveSmallIntegerField(default=0)
    saturday_minutes = models.PositiveSmallIntegerField(default=0)
    sunday_minutes = models.PositiveSmallIntegerField(default=0)

    # Under a flexitime agreement only the weekly total is owed, and the figure
    # credited for a holiday or an absence is this notional day rather than the
    # scheduled one. Leaving it null means the scheduled day is used.
    is_flexible = models.BooleanField(default=False)
    notional_daily_minutes = models.PositiveSmallIntegerField(null=True, blank=True)

    # Ordered Monday-first to match date.weekday().
    WEEKDAY_FIELDS = (
        "monday_minutes",
        "tuesday_minutes",
        "wednesday_minutes",
        "thursday_minutes",
        "friday_minutes",
        "saturday_minutes",
        "sunday_minutes",
    )

    def minutes_for(self, day):
        """Scheduled minutes for a date. Zero on a weekday this person does not work."""
        return getattr(self, self.WEEKDAY_FIELDS[day.weekday()])

    @property
    def weekly_minutes(self):
        return sum(getattr(self, field) for field in self.WEEKDAY_FIELDS)

    def __str__(self):
        owner = self.profile_id or "workspace default"
        return f"{owner} from {self.valid_from}"

    class Meta:
        verbose_name = "HR Work Schedule"
        verbose_name_plural = "HR Work Schedules"
        db_table = "hr_work_schedules"
        ordering = ("-valid_from",)
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "valid_from"],
                condition=models.Q(profile__isnull=False),
                name="unique_hr_schedule_start_per_profile",
            ),
            models.UniqueConstraint(
                fields=["workspace", "valid_from"],
                condition=models.Q(profile__isnull=True),
                name="unique_hr_default_schedule_start",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=models.F("valid_from")),
                name="hr_schedule_valid_range",
            ),
        ]
        indexes = [models.Index(fields=["profile", "valid_from", "valid_to"])]


class HrHolidayCalendar(HrBaseModel):
    """A named set of non-working days, so people in different places can differ."""

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_holiday_calendars",
    )
    name = models.CharField(max_length=120)
    country_code = models.CharField(max_length=2)
    # Austria's statutory holidays are federal and identical everywhere, so this
    # only carries weight for Germany and for days granted by agreement.
    region_code = models.CharField(max_length=8, blank=True, default="")
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.country_code})"

    class Meta:
        verbose_name = "HR Holiday Calendar"
        verbose_name_plural = "HR Holiday Calendars"
        db_table = "hr_holiday_calendars"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "country_code", "region_code"],
                name="unique_hr_holiday_calendar_region",
            ),
            # Exactly one fallback. With two, whoever has no calendar of their own
            # would get whichever happened to sort first, and a whole group of
            # people would quietly be on the wrong holidays.
            models.UniqueConstraint(
                fields=["workspace"],
                condition=models.Q(is_default=True),
                name="unique_hr_default_holiday_calendar",
            ),
        ]


class HrHoliday(HrBaseModel):
    """One non-working day, possibly only half of one."""

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="hr_holidays",
    )
    calendar = models.ForeignKey(
        HrHolidayCalendar,
        on_delete=models.CASCADE,
        related_name="holidays",
    )
    date = models.DateField()
    name_de = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True, default="")
    # 24 and 31 December are commonly half days by agreement rather than statute.
    day_fraction = models.DecimalField(max_digits=3, decimal_places=2, default=1)
    # Separates a statutory holiday, which carries a pay entitlement, from a day
    # the company grants.
    is_statutory = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.date} {self.name_de}"

    class Meta:
        verbose_name = "HR Holiday"
        verbose_name_plural = "HR Holidays"
        db_table = "hr_holidays"
        ordering = ("date",)
        constraints = [
            models.UniqueConstraint(fields=["calendar", "date"], name="unique_hr_holiday_per_calendar"),
            models.CheckConstraint(
                condition=models.Q(day_fraction__gt=0) & models.Q(day_fraction__lte=1),
                name="hr_holiday_fraction_range",
            ),
        ]
        indexes = [models.Index(fields=["calendar", "date"])]
