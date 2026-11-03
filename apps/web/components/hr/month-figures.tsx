/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// services
import type { THrAttendanceDay, THrMe } from "@/services/hr.service";
// local imports
import { HrDayTable } from "./day-table";
import { HrMonthSummary } from "./month-summary";
import { useRunningMinutes, withRunningTimer } from "./running-timer";
import { HrStatementPanel } from "./statement-panel";

/** Contracted hours as the schedule in force has them, and only failing that as the contract does. */
const contractedWeeklyMinutes = (me: THrMe) => me.schedule?.weekly_minutes ?? me.contract?.weekly_minutes ?? null;

type TProps = {
  me: THrMe;
  /** Opens a day for editing. Absent where the month is only being read. */
  onPickDay?: (workDate: string) => void;
  attendance?: THrAttendanceDay[];
};

/**
 * What the month came to, what it is worth to whoever invoices it, and the
 * day-by-day behind both. Shared with the page a manager reads, so the two cannot
 * come to show different figures for the same month.
 */
export const HrMonthFigures = ({ me, onPickDay, attendance }: TProps) => {
  // A timer still running counts as it goes, so nobody has to stop it to see where they stand.
  const runningMinutes = useRunningMinutes(me.running_timer);
  const period = withRunningTimer(me.period, me.running_timer, runningMinutes);

  return (
    <>
      <HrMonthSummary
        period={period}
        hasRunningTimer={me.has_running_timer}
        runningMinutes={me.running_timer ? runningMinutes : null}
        contractedWeeklyMinutes={contractedWeeklyMinutes(me)}
        teleworkDaysThisYear={me.telework_days_this_year}
        leave={me.leave}
        schedule={me.schedule}
      />

      <HrStatementPanel periodId={period?.id ?? null} arrangement={me.contract?.arrangement ?? null} />

      <HrDayTable
        days={period?.days ?? []}
        countedThrough={period?.to_date ? period.to_date.counted_through : undefined}
        onPickDay={onPickDay}
        attendance={attendance}
        runningDay={me.running_timer?.day ?? null}
      />
    </>
  );
};
