/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { EHrDayKind, EHrPeriodState, type THrPeriod } from "@/services/hr.service";

/**
 * Everything the server sends is minutes. These turn that into something a person
 * reads, and nothing here is ever used to compute with — a figure that has been
 * through a display helper has been rounded and is not the figure any more.
 */

/** Minutes as hours and minutes, e.g. `7:42`. Negative keeps its sign at the front. */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  const sign = minutes < 0 ? "-" : "";
  const total = Math.abs(minutes);
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return `${sign}${hours}:${String(rest).padStart(2, "0")}`;
}

/** A balance, always carrying its sign so that zero and plus-zero read differently. */
export function formatBalance(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  if (minutes === 0) return "0:00";
  return `${minutes > 0 ? "+" : ""}${formatMinutes(minutes)}`;
}

/** Minutes as decimal hours, which is what payroll works in. */
export function formatDecimalHours(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  return (minutes / 60).toFixed(2);
}

export function balanceTone(minutes: number | null | undefined): string {
  if (!minutes) return "text-custom-text-200";
  return minutes > 0 ? "text-custom-primary-100" : "text-red-500";
}

// These map to translation keys rather than to text, because the mapping is
// wanted from plain functions that have no hook to reach the translator with.
// The caller has one and does the lookup.
const DAY_KIND_KEY: Record<EHrDayKind, string> = {
  [EHrDayKind.WORKDAY]: "hr.day_kind.workday",
  [EHrDayKind.NON_WORKING]: "hr.day_kind.non_working",
  [EHrDayKind.HOLIDAY]: "hr.day_kind.holiday",
  [EHrDayKind.HALF_HOLIDAY]: "hr.day_kind.half_holiday",
  [EHrDayKind.ABSENCE]: "hr.day_kind.absence",
  [EHrDayKind.PARTIAL_ABSENCE]: "hr.day_kind.partial_absence",
};

export function dayKindKey(kind: EHrDayKind): string {
  return DAY_KIND_KEY[kind] ?? "hr.day_kind.workday";
}

const PERIOD_STATE_KEY: Record<EHrPeriodState, string> = {
  [EHrPeriodState.OPEN]: "hr.state.open",
  [EHrPeriodState.SUBMITTED]: "hr.state.submitted",
  [EHrPeriodState.APPROVED]: "hr.state.approved",
  [EHrPeriodState.LOCKED]: "hr.state.closed",
  [EHrPeriodState.REOPENED]: "hr.state.reopened",
};

export function periodStateKey(state: EHrPeriodState): string {
  return PERIOD_STATE_KEY[state] ?? "hr.state.open";
}

/** A month can only be changed while it is open or has been reopened. */
export function isPeriodEditable(state: EHrPeriodState): boolean {
  return state === EHrPeriodState.OPEN || state === EHrPeriodState.REOPENED;
}

/** `2026-03-02` as `Mon 2 Mar`, without pulling in a date library. */
export function formatDayLabel(isoDate: string, locale?: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "short" });
}

/**
 * An amount as somebody would write it.
 *
 * Rates are held to four decimals so an odd one can be recorded exactly, but a
 * rate of 72.50 an hour arrives as "72.5000" and reads like a rounding error.
 * Two decimals always, and any more only where they carry something.
 */
export const tidyAmount = (amount: string | null) => {
  if (!amount) return "";
  const trimmed = amount.includes(".") ? amount.replace(/0+$/, "") : amount;
  const [whole, fraction = ""] = trimmed.split(".");

  return `${whole}.${fraction.padEnd(2, "0")}`;
};

/**
 * `2026-03-02` as `2 Mar 2026`.
 *
 * The year is kept, unlike formatDayLabel above. That one labels a day inside a
 * month somebody is already looking at, where the year is on the screen already;
 * this labels a date that can be years from the one being read, and "Mon 2 Mar"
 * on its own says nothing about which March.
 */
export function formatDayWithYear(isoDate: string, locale?: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });
}

export function formatMonthLabel(isoDate: string, locale?: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString(locale, { month: "long", year: "numeric" });
}

/** Whether a date string is today, so the current day can be marked in a list. */
export function isToday(isoDate: string): boolean {
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(
    2,
    "0"
  )}`;
  return isoDate === today;
}

/** The previous month, for stepping backwards through a year. */
export function previousMonth(year: number, month: number): [number, number] {
  return month === 1 ? [year - 1, 12] : [year, month - 1];
}

export function nextMonth(year: number, month: number): [number, number] {
  return month === 12 ? [year + 1, 1] : [year, month + 1];
}

/**
 * The figures a screen should actually show for a month.
 *
 * A month still running has two of them, and every surface has to pick the same
 * one or the summary above a table stops agreeing with the table below it. That
 * disagreement is worse than the original wrong number: a reader who adds up a
 * column and gets something else concludes the whole screen is broken.
 */
export function figuresToShow(period: {
  target_minutes: number | null;
  actual_minutes: number | null;
  balance_minutes: number | null;
  to_date?: THrPeriod["to_date"];
}) {
  const soFar = period.to_date;
  return {
    isPartial: !!soFar,
    countedThrough: soFar?.counted_through ?? null,
    target: soFar ? soFar.target_minutes : period.target_minutes,
    actual: soFar ? soFar.actual_minutes : period.actual_minutes,
    balance: soFar ? soFar.balance_minutes : period.balance_minutes,
    // The whole month stays available, because what the contract owes is still
    // worth showing next to how far through it somebody is.
    monthTarget: period.target_minutes,
  };
}

/** Whether a day has happened yet, given how far the month has been counted. */
export function hasHappened(workDate: string, countedThrough: string | null): boolean {
  if (countedThrough === null) return false;
  return workDate <= countedThrough;
}

/**
 * Read a length of time somebody typed, in minutes.
 *
 * Accepts "7:42" and "7.7" and "462m", because the screens show h:mm and people
 * copy figures out of contracts written either way. Returns null for anything it
 * cannot read, so a typo is refused rather than silently becoming zero — a zero
 * here is a real instruction that the day is not worked.
 */
export function parseDuration(input: string): number | null {
  const text = input.trim().toLowerCase();
  if (!text) return null;

  const clock = /^(\d{1,3}):([0-5]?\d)$/.exec(text);
  if (clock) return Number(clock[1]) * 60 + Number(clock[2]);

  const minutes = /^(\d{1,5})\s*m(in)?$/.exec(text);
  if (minutes) return Number(minutes[1]);

  const hours = /^(\d{1,3})([.,](\d{1,4}))?\s*h?$/.exec(text);
  if (hours) {
    const whole = Number(hours[1]);
    const fraction = hours[3] ? Number(`0.${hours[3]}`) : 0;
    return Math.round((whole + fraction) * 60);
  }
  return null;
}
