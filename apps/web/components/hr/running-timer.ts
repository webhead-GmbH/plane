/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
// services
import type { THrPeriod, THrRunningTimer } from "@/services/hr.service";

/** How often the minutes of a running timer are counted again: often enough for a clock that shows minutes. */
const TICK_MS = 15_000;

/** Whole minutes a timer has been running, counted again as it goes; 0 when none is. */
export const useRunningMinutes = (timer: THrRunningTimer | null | undefined) => {
  const startedAt = timer?.started_at;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!startedAt) return;
    const id = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(id);
  }, [startedAt]);

  if (!startedAt) return 0;
  return Math.max(0, Math.floor((now - Date.parse(startedAt)) / 60_000));
};

const plus = (value: number | null, minutes: number) => (value ?? 0) + minutes;

/**
 * The month with a running timer's minutes so far added where they will count:
 * on the day it started, as work on a work item. The server leaves them out until
 * the timer stops, since until then they have no length; adding them here lets
 * somebody see how the day and the month stand without stopping the clock.
 */
export const withRunningTimer = (
  period: THrPeriod | null,
  timer: THrRunningTimer | null | undefined,
  minutes: number
): THrPeriod | null => {
  const day = timer?.day;
  if (!period || !day || minutes <= 0) return period;

  const days = period.days?.map((row) =>
    row.work_date === day
      ? Object.assign({}, row, {
          project_minutes: row.project_minutes + minutes,
          actual_minutes: row.actual_minutes + minutes,
          balance_minutes: row.balance_minutes + minutes,
        })
      : row
  );
  const toDate = period.to_date;
  // A month still running counts so far only up to its last counted day.
  const countsSoFar = Boolean(toDate?.counted_through && day <= toDate.counted_through);

  return Object.assign({}, period, {
    days,
    project_minutes: plus(period.project_minutes, minutes),
    actual_minutes: plus(period.actual_minutes, minutes),
    balance_minutes: plus(period.balance_minutes, minutes),
    to_date:
      toDate && countsSoFar
        ? Object.assign({}, toDate, {
            project_minutes: toDate.project_minutes + minutes,
            actual_minutes: toDate.actual_minutes + minutes,
            balance_minutes: toDate.balance_minutes + minutes,
          })
        : toDate,
  });
};
