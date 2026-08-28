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

const DAY_KIND_LABEL: Record<EHrDayKind, string> = {
  [EHrDayKind.WORKDAY]: "Working day",
  [EHrDayKind.NON_WORKING]: "Not a working day",
  [EHrDayKind.HOLIDAY]: "Public holiday",
  [EHrDayKind.HALF_HOLIDAY]: "Half holiday",
  [EHrDayKind.ABSENCE]: "Away",
  [EHrDayKind.PARTIAL_ABSENCE]: "Partly away",
};

export function dayKindLabel(kind: EHrDayKind): string {
  return DAY_KIND_LABEL[kind] ?? "Working day";
}

const PERIOD_STATE_LABEL: Record<EHrPeriodState, string> = {
  [EHrPeriodState.OPEN]: "Open",
  [EHrPeriodState.SUBMITTED]: "Submitted",
  [EHrPeriodState.APPROVED]: "Approved",
  [EHrPeriodState.LOCKED]: "Closed",
  [EHrPeriodState.REOPENED]: "Reopened",
};

export function periodStateLabel(state: EHrPeriodState): string {
  return PERIOD_STATE_LABEL[state] ?? "Open";
}

/** A month can only be changed while it is open or has been reopened. */
export function isPeriodEditable(state: EHrPeriodState): boolean {
  return state === EHrPeriodState.OPEN || state === EHrPeriodState.REOPENED;
}

/** `2026-03-02` as `Mon 2 Mar`, without pulling in a date library. */
export function formatDayLabel(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

export function formatMonthLabel(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString(undefined, { month: "long", year: "numeric" });
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
