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
};

export type THrEmploymentProfile = {
  id: string;
  member: string;
  member_display_name: string;
  member_email: string;
  member_avatar_url: string;
  timezone: string;
  hire_date: string | null;
  is_hr_manager: boolean;
  is_active: boolean;
};

export type THrContract = {
  id: string;
  valid_from: string;
  valid_to: string | null;
  arrangement: string;
  records_target_hours: boolean;
  records_attendance: boolean;
  records_leave_account: boolean;
  weekly_minutes: number | null;
  agreed_scope_minutes: number | null;
};

export type THrWorkSchedule = {
  id: string;
  name: string;
  valid_from: string;
  monday_minutes: number;
  tuesday_minutes: number;
  wednesday_minutes: number;
  thursday_minutes: number;
  friday_minutes: number;
  saturday_minutes: number;
  sunday_minutes: number;
  weekly_minutes: number;
  is_flexible: boolean;
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

  async deleteTimeEntry(entryId: string) {
    return this.delete(`${this.base}/time-entries/${entryId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async timeEntries(from: string, to: string): Promise<THrTimeEntry[]> {
    return this.get(`${this.base}/time-entries/?from=${from}&to=${to}`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
