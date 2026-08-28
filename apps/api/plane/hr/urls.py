# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""No workspace appears in any of these paths, deliberately.

Employment, hours and the monthly figures belong to the person and the company,
not to whichever workspace somebody was looking at when they opened the page.
Putting a workspace in the path would make it possible — and eventually likely —
for the answer to depend on which one, and the answer must never depend on which
one.
"""

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
    HrSetupEndpoint,
    HrStatementEndpoint,
    HrTimeEntryEndpoint,
    HrWorkScheduleEndpoint,
)

urlpatterns = [
    # The person's own view, and the manager's month
    path("me/", HrMeEndpoint.as_view(), name="hr-me"),
    path("overview/", HrOverviewEndpoint.as_view(), name="hr-overview"),
    path("setup/", HrSetupEndpoint.as_view(), name="hr-setup"),
    # Months
    path("periods/", HrPeriodListEndpoint.as_view(), name="hr-periods"),
    path("periods/<uuid:pk>/", HrPeriodDetailEndpoint.as_view(), name="hr-period-detail"),
    path("periods/<uuid:pk>/days/", HrPeriodDaysEndpoint.as_view(), name="hr-period-days"),
    path(
        "periods/<uuid:pk>/days/<uuid:day_id>/settle/",
        HrPeriodDaySettleEndpoint.as_view(),
        name="hr-period-day-settle",
    ),
    path("periods/<uuid:pk>/recompute/", HrPeriodRecomputeEndpoint.as_view(), name="hr-period-recompute"),
    path("periods/<uuid:pk>/submit/", HrPeriodSubmitEndpoint.as_view(), name="hr-period-submit"),
    path("periods/<uuid:pk>/approve/", HrPeriodApproveEndpoint.as_view(), name="hr-period-approve"),
    path("periods/<uuid:pk>/lock/", HrPeriodLockEndpoint.as_view(), name="hr-period-lock"),
    path("periods/<uuid:pk>/reopen/", HrPeriodReopenEndpoint.as_view(), name="hr-period-reopen"),
    path("periods/<uuid:pk>/export/", HrPeriodExportEndpoint.as_view(), name="hr-period-export"),
    path("periods/<uuid:pk>/statement/", HrStatementEndpoint.as_view(), name="hr-period-statement"),
    # Old data in, finished months out
    path("export/", HrMonthExportEndpoint.as_view(), name="hr-month-export"),
    path("imports/", HrImportEndpoint.as_view(), name="hr-imports"),
    path("imports/<uuid:pk>/", HrImportEndpoint.as_view(), name="hr-import-detail"),
    path("imports/<uuid:pk>/commit/", HrImportCommitEndpoint.as_view(), name="hr-import-commit"),
    path("imports/<uuid:pk>/undo/", HrImportUndoEndpoint.as_view(), name="hr-import-undo"),
    # People and their terms
    path("employees/", HrEmploymentProfileEndpoint.as_view(), name="hr-employees"),
    path("employees/<uuid:pk>/", HrEmploymentProfileEndpoint.as_view(), name="hr-employee-detail"),
    path("employees/<uuid:profile_id>/contracts/", HrContractEndpoint.as_view(), name="hr-contracts"),
    path(
        "employees/<uuid:profile_id>/contracts/<uuid:pk>/",
        HrContractEndpoint.as_view(),
        name="hr-contract-detail",
    ),
    path("employees/<uuid:profile_id>/leave/", HrLeaveEntitlementEndpoint.as_view(), name="hr-leave"),
    path(
        "employees/<uuid:profile_id>/leave/<uuid:pk>/",
        HrLeaveEntitlementEndpoint.as_view(),
        name="hr-leave-detail",
    ),
    path(
        "employees/<uuid:profile_id>/opening-balances/",
        HrOpeningBalanceEndpoint.as_view(),
        name="hr-opening-balances",
    ),
    path(
        "employees/<uuid:profile_id>/opening-balances/<uuid:pk>/",
        HrOpeningBalanceEndpoint.as_view(),
        name="hr-opening-balance-detail",
    ),
    # When people are expected to work, and when nobody does
    path("schedules/", HrWorkScheduleEndpoint.as_view(), name="hr-schedules"),
    path("schedules/<uuid:pk>/", HrWorkScheduleEndpoint.as_view(), name="hr-schedule-detail"),
    path("holiday-calendars/", HrHolidayCalendarEndpoint.as_view(), name="hr-holiday-calendars"),
    path(
        "holiday-calendars/<uuid:pk>/",
        HrHolidayCalendarEndpoint.as_view(),
        name="hr-holiday-calendar-detail",
    ),
    path("holidays/", HrHolidayEndpoint.as_view(), name="hr-holidays"),
    path("holidays/<uuid:pk>/", HrHolidayEndpoint.as_view(), name="hr-holiday-detail"),
    # Absence
    path("absence-types/", HrAbsenceTypeEndpoint.as_view(), name="hr-absence-types"),
    path("absence-types/<uuid:pk>/", HrAbsenceTypeEndpoint.as_view(), name="hr-absence-type-detail"),
    path("absences/", HrAbsenceEndpoint.as_view(), name="hr-absences"),
    path("absences/calendar/", HrAbsenceCalendarEndpoint.as_view(), name="hr-absence-calendar"),
    path("absences/<uuid:pk>/", HrAbsenceEndpoint.as_view(), name="hr-absence-detail"),
    path(
        "absences/<uuid:pk>/<str:decision>/",
        HrAbsenceDecisionEndpoint.as_view(),
        name="hr-absence-decision",
    ),
    # Hours with no work item behind them
    path("time-entries/", HrTimeEntryEndpoint.as_view(), name="hr-time-entries"),
    path("time-entries/<uuid:pk>/", HrTimeEntryEndpoint.as_view(), name="hr-time-entry-detail"),
    # Rates and invoices
    path("rate-cards/", HrRateCardEndpoint.as_view(), name="hr-rate-cards"),
    path("rate-cards/<uuid:pk>/", HrRateCardEndpoint.as_view(), name="hr-rate-card-detail"),
    path("invoices/", HrInvoiceEndpoint.as_view(), name="hr-invoices"),
    path("invoices/<uuid:pk>/", HrInvoiceEndpoint.as_view(), name="hr-invoice-detail"),
    path("invoices/<uuid:pk>/reconcile/", HrInvoiceReconcileEndpoint.as_view(), name="hr-invoice-reconcile"),
    path(
        "invoices/<uuid:pk>/accept-variance/",
        HrInvoiceAcceptVarianceEndpoint.as_view(),
        name="hr-invoice-accept-variance",
    ),
]
