# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from .base import HrWorkspaceConfigEndpoint
from .master_data import (
    HrAbsenceTypeEndpoint,
    HrContractEndpoint,
    HrEmploymentProfileEndpoint,
    HrHolidayCalendarEndpoint,
    HrHolidayEndpoint,
    HrLeaveEntitlementEndpoint,
    HrWorkScheduleEndpoint,
    HrWorkspaceBootstrapEndpoint,
)
from .period import (
    HrMeEndpoint,
    HrOverviewEndpoint,
    HrPeriodApproveEndpoint,
    HrPeriodDaySettleEndpoint,
    HrPeriodDaysEndpoint,
    HrPeriodDetailEndpoint,
    HrPeriodListEndpoint,
    HrPeriodLockEndpoint,
    HrPeriodRecomputeEndpoint,
    HrPeriodReopenEndpoint,
    HrPeriodSubmitEndpoint,
)
from .transfer import (
    HrImportCommitEndpoint,
    HrImportEndpoint,
    HrImportUndoEndpoint,
    HrMonthExportEndpoint,
    HrOpeningBalanceEndpoint,
    HrPeriodExportEndpoint,
)
from .records import (
    HrAbsenceCalendarEndpoint,
    HrAbsenceDecisionEndpoint,
    HrAbsenceEndpoint,
    HrTimeEntryEndpoint,
)

__all__ = [
    "HrAbsenceCalendarEndpoint",
    "HrAbsenceDecisionEndpoint",
    "HrAbsenceEndpoint",
    "HrAbsenceTypeEndpoint",
    "HrContractEndpoint",
    "HrEmploymentProfileEndpoint",
    "HrHolidayCalendarEndpoint",
    "HrHolidayEndpoint",
    "HrImportCommitEndpoint",
    "HrImportEndpoint",
    "HrImportUndoEndpoint",
    "HrLeaveEntitlementEndpoint",
    "HrMeEndpoint",
    "HrMonthExportEndpoint",
    "HrOpeningBalanceEndpoint",
    "HrOverviewEndpoint",
    "HrPeriodApproveEndpoint",
    "HrPeriodDaySettleEndpoint",
    "HrPeriodDaysEndpoint",
    "HrPeriodDetailEndpoint",
    "HrPeriodExportEndpoint",
    "HrPeriodListEndpoint",
    "HrPeriodLockEndpoint",
    "HrPeriodRecomputeEndpoint",
    "HrPeriodReopenEndpoint",
    "HrPeriodSubmitEndpoint",
    "HrTimeEntryEndpoint",
    "HrWorkScheduleEndpoint",
    "HrWorkspaceBootstrapEndpoint",
    "HrWorkspaceConfigEndpoint",
]
