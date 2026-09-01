/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

/**
 * Types live here rather than in the shared types package. Nothing outside this
 * feature uses them, and keeping them local means the package does not have to be
 * rebuilt every time a field is added.
 *
 * Every duration is minutes, exactly as the server holds it. Converting to hours
 * is a display decision and is made once, at the point of display.
 */

/** How a day turned out. Mirrors the day kinds the server reports. */
export enum EHrDayKind {
  WORKDAY = 10,
  NON_WORKING = 20,
  HOLIDAY = 30,
  HALF_HOLIDAY = 40,
  ABSENCE = 50,
  PARTIAL_ABSENCE = 60,
}

/** How far through closing a month is. */
export enum EHrPeriodState {
  OPEN = 10,
  SUBMITTED = 20,
  APPROVED = 30,
  LOCKED = 40,
  REOPENED = 50,
}

export type THrPeriodDay = {
  id: string;
  work_date: string;
  target_minutes: number;
  project_minutes: number;
  non_project_minutes: number;
  attendance_minutes: number | null;
  absence_minutes: number;
  holiday_minutes: number;
  actual_minutes: number;
  balance_minutes: number;
  day_kind: EHrDayKind;
  needs_review: boolean;
  note: string;
  last_rebuilt_at: string | null;
};

/**
 * Where somebody stands part-way through a month.
 *
 * Present only while a month is still running. Its absence means the month is
 * its own answer — which is why a screen must check for the block rather than
 * compare a date, or every finished month reads as one where nothing counted.
 */
export type THrPeriodToDate = {
  counted_through: string | null;
  target_minutes: number;
  actual_minutes: number;
  balance_minutes: number;
  project_minutes: number;
  non_project_minutes: number;
  absence_minutes: number;
  holiday_minutes: number;
};

export type THrPeriod = {
  id: string;
  profile: string;
  member_display_name?: string;
  period_start: string;
  period_end: string;
  state: EHrPeriodState;
  target_minutes: number | null;
  actual_minutes: number | null;
  balance_minutes: number | null;
  opening_balance_minutes: number | null;
  closing_balance_minutes: number | null;
  project_minutes: number | null;
  non_project_minutes: number | null;
  absence_minutes: number | null;
  holiday_minutes: number | null;
  leave_consumed_minutes: number | null;
  submitted_at: string | null;
  approved_at: string | null;
  locked_at: string | null;
  days?: THrPeriodDay[];
  has_running_timer?: boolean;
  to_date?: THrPeriodToDate;
};

/** The four arrangements the company actually employs people under. */
export enum EHrArrangement {
  REMOTE_FULL_TIME_INVOICING = "remote_full_time_invoicing",
  REMOTE_PART_TIME_INVOICING = "remote_part_time_invoicing",
  ONSITE_PART_TIME = "onsite_part_time",
  ONSITE_FULL_TIME = "onsite_full_time",
}

export enum EHrLegalForm {
  EMPLOYEE = "employee",
  FREE_SERVICE = "free_service",
  CONTRACT_FOR_WORK = "contract_for_work",
}

/** Somebody who could be given an employment record but has none. */
export type THrCandidate = {
  id: string;
  display_name: string;
  email: string;
  avatar_url: string;
};

export type THrEmploymentProfile = {
  id: string;
  member: string;
  member_display_name: string;
  member_email: string;
  member_avatar_url: string;
  timezone: string;
  holiday_calendar: string | null;
  hire_date: string | null;
  exit_date: string | null;
  is_hr_manager: boolean;
  is_active: boolean;
};

export type THrContract = {
  id: string;
  profile: string;
  valid_from: string;
  valid_to: string | null;
  arrangement: EHrArrangement;
  legal_form: EHrLegalForm | null;
  records_target_hours: boolean;
  records_attendance: boolean;
  records_leave_account: boolean;
  weekly_minutes: number | null;
  agreed_scope_minutes: number | null;
};

export type THrWorkSchedule = {
  id: string;
  /** Null for the company default that applies to anyone without one of their own. */
  profile: string | null;
  name: string;
  valid_from: string;
  valid_to: string | null;
  monday_minutes: number;
  tuesday_minutes: number;
  wednesday_minutes: number;
  thursday_minutes: number;
  friday_minutes: number;
  saturday_minutes: number;
  sunday_minutes: number;
  weekly_minutes: number;
  is_flexible: boolean;
  notional_daily_minutes: number | null;
};

/** Everything the personal view needs, in one response. */
export type THrMe = {
  profile: THrEmploymentProfile | null;
  is_hr_manager: boolean;
  contract: THrContract | null;
  schedule: THrWorkSchedule | null;
  period: THrPeriod | null;
  has_running_timer: boolean;
};

/** One person's row in the manager's month. */
export type THrOverviewRow = THrPeriod & {
  member_display_name: string;
  needs_review: boolean;
  has_running_timer: boolean;
};

export type THrOverview = {
  year: number;
  month: number;
  rows: THrOverviewRow[];
};

export type THrStatement = {
  period_id: string;
  period_start: string;
  period_end: string;
  state: EHrPeriodState;
  is_final: boolean;
  minutes: number;
  hours: string;
  currency: string;
  hourly_rate: string | null;
  expected_amount: string | null;
  has_rate: boolean;
};

/** What an hour with no work item behind it was spent on. */
export enum EHrTimeCategory {
  MEETING = 10,
  TRAINING = 20,
  ADMIN = 30,
  TRAVEL = 40,
  ON_CALL = 50,
  CORRECTION = 60,
  IMPORTED = 70,
}

/** Where a record came from, which is what tells hand-entered from imported. */
export enum EHrTimeSource {
  MANUAL = 10,
  IMPORT = 20,
  SYSTEM = 30,
}

export type THrTimeEntry = {
  id: string;
  profile: string;
  entry_date: string;
  minutes: number;
  category: number;
  source: number;
  note: string;
  locked_period: string | null;
};

/** What a file being brought in holds. */
export enum EHrImportKind {
  TIME_ENTRIES = 10,
  ABSENCES = 20,
  OPENING_BALANCES = 30,
}

export enum EHrImportState {
  UPLOADED = 10,
  VALIDATING = 20,
  PREVIEW_READY = 30,
  COMMITTING = 40,
  COMMITTED = 50,
  FAILED = 60,
  ROLLED_BACK = 70,
}

export type THrImportRow = {
  row: number;
  verdict: "ok" | "error" | "skip";
  message: string;
  data: Record<string, unknown>;
};

export type THrImportBatch = {
  id: string;
  kind: EHrImportKind;
  state: EHrImportState;
  filename: string;
  row_count: number;
  valid_count: number;
  error_count: number;
  skipped_count: number;
  preview: THrImportRow[];
  committed_at: string | null;
  rolled_back_at: string | null;
  rollback_reason: string | null;
};

export class HrService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  // No workspace in any of these paths. The workspaces on this installation
  // belong to one company and the people in them are the same people, so somebody
  // reaches their own hours and their own month from wherever they happen to be.
  private base = "/api/hr";

  async me(year?: number, month?: number): Promise<THrMe> {
    const query = year && month ? `?year=${year}&month=${month}` : "";
    return this.get(`${this.base}/me/${query}`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async overview(year?: number, month?: number): Promise<THrOverview> {
    const query = year && month ? `?year=${year}&month=${month}` : "";
    return this.get(`${this.base}/overview/${query}`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async approve(periodId: string): Promise<THrPeriod> {
    return this.post(`${this.base}/periods/${periodId}/approve/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async lock(periodId: string): Promise<THrPeriod> {
    return this.post(`${this.base}/periods/${periodId}/lock/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async reopen(periodId: string, reason: string): Promise<THrPeriod> {
    return this.post(`${this.base}/periods/${periodId}/reopen/`, { reason })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** The payroll export for a whole month, as a file. */
  monthExportUrl(year: number, month: number, fileFormat: "csv" | "xlsx"): string {
    return `${this.base}/export/?year=${year}&month=${month}&file_format=${fileFormat}`;
  }

  async periods(year?: number): Promise<THrPeriod[]> {
    const query = year ? `?year=${year}` : "";
    return this.get(`${this.base}/periods/${query}`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async periodDays(periodId: string): Promise<THrPeriodDay[]> {
    return this.get(`${this.base}/periods/${periodId}/days/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async recompute(periodId: string): Promise<THrPeriod> {
    return this.post(`${this.base}/periods/${periodId}/recompute/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async submit(periodId: string): Promise<THrPeriod> {
    return this.post(`${this.base}/periods/${periodId}/submit/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async statement(periodId: string): Promise<THrStatement> {
    return this.get(`${this.base}/periods/${periodId}/statement/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createTimeEntry(data: Partial<THrTimeEntry> & { profile_id: string }) {
    return this.post(`${this.base}/time-entries/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateTimeEntry(entryId: string, data: Partial<THrTimeEntry>) {
    return this.patch(`${this.base}/time-entries/${entryId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async deleteTimeEntry(entryId: string) {
    return this.delete(`${this.base}/time-entries/${entryId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Non-project hours in a date window.
   *
   * Always ask for one person. Left unscoped this returns everyone the caller may
   * see, which for a manager is the whole company — so a screen showing one
   * person's day would quietly list, and offer to delete, their colleagues' hours.
   */
  async timeEntries(from: string, to: string, profileId: string): Promise<THrTimeEntry[]> {
    return this.get(`${this.base}/time-entries/?from=${from}&to=${to}&profile_id=${profileId}`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  // ---------------------------------------------------------------------------
  // Master data. Company-wide like everything else here, and only reachable by
  // whoever looks after the team.
  // ---------------------------------------------------------------------------

  async candidates(): Promise<THrCandidate[]> {
    return this.get(`${this.base}/candidates/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async employees(): Promise<THrEmploymentProfile[]> {
    return this.get(`${this.base}/employees/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createEmployee(payload: Partial<THrEmploymentProfile>): Promise<THrEmploymentProfile> {
    return this.post(`${this.base}/employees/`, payload)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateEmployee(profileId: string, payload: Partial<THrEmploymentProfile>): Promise<THrEmploymentProfile> {
    return this.patch(`${this.base}/employees/${profileId}/`, payload)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Marks somebody as having left. Their closed months stay readable. */
  async removeEmployee(profileId: string) {
    return this.delete(`${this.base}/employees/${profileId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async contracts(profileId: string): Promise<THrContract[]> {
    return this.get(`${this.base}/employees/${profileId}/contracts/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createContract(profileId: string, payload: Partial<THrContract>): Promise<THrContract> {
    return this.post(`${this.base}/employees/${profileId}/contracts/`, payload)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateContract(profileId: string, contractId: string, payload: Partial<THrContract>): Promise<THrContract> {
    return this.patch(`${this.base}/employees/${profileId}/contracts/${contractId}/`, payload)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async deleteContract(profileId: string, contractId: string) {
    return this.delete(`${this.base}/employees/${profileId}/contracts/${contractId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async schedules(): Promise<THrWorkSchedule[]> {
    return this.get(`${this.base}/schedules/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createSchedule(payload: Partial<THrWorkSchedule>): Promise<THrWorkSchedule> {
    return this.post(`${this.base}/schedules/`, payload)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateSchedule(scheduleId: string, payload: Partial<THrWorkSchedule>): Promise<THrWorkSchedule> {
    return this.patch(`${this.base}/schedules/${scheduleId}/`, payload)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async deleteSchedule(scheduleId: string) {
    return this.delete(`${this.base}/schedules/${scheduleId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  // ---------------------------------------------------------------------------
  // Bringing months in from whatever recorded them before.
  // ---------------------------------------------------------------------------

  async imports(): Promise<THrImportBatch[]> {
    return this.get(`${this.base}/imports/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Uploads a file and returns what it WOULD do. Nothing is written yet. */
  async checkImport(file: File, kind: EHrImportKind): Promise<THrImportBatch> {
    const body = new FormData();
    body.append("file", file);
    body.append("kind", String(kind));
    // The boundary is axios's to set from the FormData; naming the content type
    // here would send one without it and the file would arrive unreadable.
    return this.post(`${this.base}/imports/`, body)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async applyImport(batchId: string): Promise<THrImportBatch & { written: number }> {
    return this.post(`${this.base}/imports/${batchId}/commit/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async undoImport(batchId: string, reason: string): Promise<THrImportBatch & { removed: number }> {
    return this.post(`${this.base}/imports/${batchId}/undo/`, { reason })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
