# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from .base import HrBaseSerializer
from .records import (
    HrAbsenceSerializer,
    HrAbsenceTypeSerializer,
    HrAttendanceDaySerializer,
    HrContractSerializer,
    HrEmploymentProfileSerializer,
    HrHolidayCalendarSerializer,
    HrHolidaySerializer,
    HrLeaveEntitlementSerializer,
    HrPeriodDaySerializer,
    HrPeriodSerializer,
    HrTeamAbsenceSerializer,
    HrTimeEntrySerializer,
    HrWorkScheduleSerializer,
)

__all__ = [
    "HrAbsenceSerializer",
    "HrAbsenceTypeSerializer",
    "HrAttendanceDaySerializer",
    "HrBaseSerializer",
    "HrContractSerializer",
    "HrEmploymentProfileSerializer",
    "HrHolidayCalendarSerializer",
    "HrHolidaySerializer",
    "HrLeaveEntitlementSerializer",
    "HrPeriodDaySerializer",
    "HrPeriodSerializer",
    "HrTeamAbsenceSerializer",
    "HrTimeEntrySerializer",
    "HrWorkScheduleSerializer",
]
