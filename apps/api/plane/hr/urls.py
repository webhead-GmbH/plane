# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.hr.api.views import (
    HrAbsenceCalendarEndpoint,
    HrAbsenceDecisionEndpoint,
    HrAbsenceEndpoint,
    HrAbsenceTypeEndpoint,
    HrContractEndpoint,
    HrEmploymentProfileEndpoint,
    HrHolidayCalendarEndpoint,
    HrHolidayEndpoint,
    HrImportCommitEndpoint,
    HrImportEndpoint,
    HrImportUndoEndpoint,
    HrInvoiceAcceptVarianceEndpoint,
    HrInvoiceEndpoint,
    HrInvoiceReconcileEndpoint,
    HrLeaveEntitlementEndpoint,
    HrMeEndpoint,
    HrMonthExportEndpoint,
    HrOpeningBalanceEndpoint,
    HrOverviewEndpoint,
    HrPeriodApproveEndpoint,
    HrPeriodDaySettleEndpoint,
    HrPeriodDaysEndpoint,
    HrPeriodDetailEndpoint,
    HrPeriodExportEndpoint,
    HrPeriodListEndpoint,
    HrPeriodLockEndpoint,
    HrPeriodRecomputeEndpoint,
    HrPeriodReopenEndpoint,
    HrPeriodSubmitEndpoint,
    HrRateCardEndpoint,
    HrStatementEndpoint,
    HrTimeEntryEndpoint,
    HrWorkScheduleEndpoint,
    HrWorkspaceBootstrapEndpoint,
)

WS = "workspaces/<str:slug>"

urlpatterns = [
    # The person's own view, and the manager's month
    path(f"{WS}/me/", HrMeEndpoint.as_view(), name="hr-me"),
    path(f"{WS}/overview/", HrOverviewEndpoint.as_view(), name="hr-overview"),
    path(f"{WS}/bootstrap/", HrWorkspaceBootstrapEndpoint.as_view(), name="hr-bootstrap"),
    # Months
    path(f"{WS}/periods/", HrPeriodListEndpoint.as_view(), name="hr-periods"),
    path(f"{WS}/periods/<uuid:pk>/", HrPeriodDetailEndpoint.as_view(), name="hr-period-detail"),
    path(f"{WS}/periods/<uuid:pk>/days/", HrPeriodDaysEndpoint.as_view(), name="hr-period-days"),
    path(
        f"{WS}/periods/<uuid:pk>/days/<uuid:day_id>/settle/",
        HrPeriodDaySettleEndpoint.as_view(),
        name="hr-period-day-settle",
    ),
    path(
        f"{WS}/periods/<uuid:pk>/recompute/",
        HrPeriodRecomputeEndpoint.as_view(),
        name="hr-period-recompute",
    ),
    path(f"{WS}/periods/<uuid:pk>/submit/", HrPeriodSubmitEndpoint.as_view(), name="hr-period-submit"),
    path(
        f"{WS}/periods/<uuid:pk>/approve/",
        HrPeriodApproveEndpoint.as_view(),
        name="hr-period-approve",
    ),
    path(f"{WS}/periods/<uuid:pk>/lock/", HrPeriodLockEndpoint.as_view(), name="hr-period-lock"),
    path(f"{WS}/periods/<uuid:pk>/reopen/", HrPeriodReopenEndpoint.as_view(), name="hr-period-reopen"),
    path(f"{WS}/periods/<uuid:pk>/export/", HrPeriodExportEndpoint.as_view(), name="hr-period-export"),
    # Old data in, finished months out
    path(f"{WS}/export/", HrMonthExportEndpoint.as_view(), name="hr-month-export"),
    path(f"{WS}/imports/", HrImportEndpoint.as_view(), name="hr-imports"),
    path(f"{WS}/imports/<uuid:pk>/", HrImportEndpoint.as_view(), name="hr-import-detail"),
    path(f"{WS}/imports/<uuid:pk>/commit/", HrImportCommitEndpoint.as_view(), name="hr-import-commit"),
    path(f"{WS}/imports/<uuid:pk>/undo/", HrImportUndoEndpoint.as_view(), name="hr-import-undo"),
    path(
        f"{WS}/employees/<uuid:profile_id>/opening-balances/",
        HrOpeningBalanceEndpoint.as_view(),
        name="hr-opening-balances",
    ),
    path(
        f"{WS}/employees/<uuid:profile_id>/opening-balances/<uuid:pk>/",
        HrOpeningBalanceEndpoint.as_view(),
        name="hr-opening-balance-detail",
    ),
    # People and their terms
    path(f"{WS}/employees/", HrEmploymentProfileEndpoint.as_view(), name="hr-employees"),
    path(
        f"{WS}/employees/<uuid:pk>/",
        HrEmploymentProfileEndpoint.as_view(),
        name="hr-employee-detail",
    ),
    path(
        f"{WS}/employees/<uuid:profile_id>/contracts/",
        HrContractEndpoint.as_view(),
        name="hr-contracts",
    ),
    path(
        f"{WS}/employees/<uuid:profile_id>/contracts/<uuid:pk>/",
        HrContractEndpoint.as_view(),
        name="hr-contract-detail",
    ),
    path(
        f"{WS}/employees/<uuid:profile_id>/leave/",
        HrLeaveEntitlementEndpoint.as_view(),
        name="hr-leave",
    ),
    path(
        f"{WS}/employees/<uuid:profile_id>/leave/<uuid:pk>/",
        HrLeaveEntitlementEndpoint.as_view(),
        name="hr-leave-detail",
    ),
    # When people are expected to work, and when nobody does
    path(f"{WS}/schedules/", HrWorkScheduleEndpoint.as_view(), name="hr-schedules"),
    path(f"{WS}/schedules/<uuid:pk>/", HrWorkScheduleEndpoint.as_view(), name="hr-schedule-detail"),
    path(
        f"{WS}/holiday-calendars/",
        HrHolidayCalendarEndpoint.as_view(),
        name="hr-holiday-calendars",
    ),
    path(
        f"{WS}/holiday-calendars/<uuid:pk>/",
        HrHolidayCalendarEndpoint.as_view(),
        name="hr-holiday-calendar-detail",
    ),
    path(f"{WS}/holidays/", HrHolidayEndpoint.as_view(), name="hr-holidays"),
    path(f"{WS}/holidays/<uuid:pk>/", HrHolidayEndpoint.as_view(), name="hr-holiday-detail"),
    # Absence
    path(f"{WS}/absence-types/", HrAbsenceTypeEndpoint.as_view(), name="hr-absence-types"),
    path(
        f"{WS}/absence-types/<uuid:pk>/",
        HrAbsenceTypeEndpoint.as_view(),
        name="hr-absence-type-detail",
    ),
    path(f"{WS}/absences/", HrAbsenceEndpoint.as_view(), name="hr-absences"),
    path(f"{WS}/absences/calendar/", HrAbsenceCalendarEndpoint.as_view(), name="hr-absence-calendar"),
    path(f"{WS}/absences/<uuid:pk>/", HrAbsenceEndpoint.as_view(), name="hr-absence-detail"),
    path(
        f"{WS}/absences/<uuid:pk>/<str:decision>/",
        HrAbsenceDecisionEndpoint.as_view(),
        name="hr-absence-decision",
    ),
    # Rates, the statement that goes out before an invoice, and the invoice
    path(f"{WS}/rate-cards/", HrRateCardEndpoint.as_view(), name="hr-rate-cards"),
    path(f"{WS}/rate-cards/<uuid:pk>/", HrRateCardEndpoint.as_view(), name="hr-rate-card-detail"),
    path(
        f"{WS}/periods/<uuid:pk>/statement/",
        HrStatementEndpoint.as_view(),
        name="hr-period-statement",
    ),
    path(f"{WS}/invoices/", HrInvoiceEndpoint.as_view(), name="hr-invoices"),
    path(f"{WS}/invoices/<uuid:pk>/", HrInvoiceEndpoint.as_view(), name="hr-invoice-detail"),
    path(
        f"{WS}/invoices/<uuid:pk>/reconcile/",
        HrInvoiceReconcileEndpoint.as_view(),
        name="hr-invoice-reconcile",
    ),
    path(
        f"{WS}/invoices/<uuid:pk>/accept-variance/",
        HrInvoiceAcceptVarianceEndpoint.as_view(),
        name="hr-invoice-accept-variance",
    ),
    # Hours with no work item behind them
    path(f"{WS}/time-entries/", HrTimeEntryEndpoint.as_view(), name="hr-time-entries"),
    path(
        f"{WS}/time-entries/<uuid:pk>/",
        HrTimeEntryEndpoint.as_view(),
        name="hr-time-entry-detail",
    ),
]
