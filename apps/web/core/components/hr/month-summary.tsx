/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AlertTriangle, Clock, Timer } from "lucide-react";
// plane imports
import { cn } from "@plane/utils";
// local imports
import { EHrPeriodState, type THrPeriod } from "@/services/hr.service";
import { balanceTone, figuresToShow, formatBalance, formatDayLabel, formatMinutes, periodStateLabel } from "./utils";

type TFigureProps = {
  label: string;
  value: string;
  hint?: string;
  tone?: string;
};

const Figure = ({ label, value, hint, tone }: TFigureProps) => (
  <div className="border-custom-border-200 bg-custom-background-100 flex flex-col gap-0.5 rounded-md border px-4 py-3">
    <span className="text-xs text-custom-text-400 font-medium tracking-wide uppercase">{label}</span>
    <span className={cn("text-2xl font-semibold tabular-nums", tone ?? "text-custom-text-100")}>{value}</span>
    {hint ? <span className="text-xs text-custom-text-400">{hint}</span> : null}
  </div>
);

type TProps = {
  period: THrPeriod | null;
  hasRunningTimer: boolean;
  contractedWeeklyMinutes?: number | null;
};

/**
 * The three figures the month comes down to, kept above everything else.
 *
 * A shortfall is only worth showing if it is seen while there is still time to do
 * something about it, so the balance is given the same weight as the hours and is
 * not tucked into a total at the bottom of a table.
 */
export const HrMonthSummary = ({ period, hasRunningTimer, contractedWeeklyMinutes }: TProps) => {
  if (!period)
    return (
      <div className="border-custom-border-200 bg-custom-background-90 text-sm text-custom-text-300 rounded-md border px-4 py-6">
        Nothing has been worked out for this month yet.
      </div>
    );

  const needsReview = (period.days ?? []).some((day) => day.needs_review);
  const isFinal = period.state === EHrPeriodState.LOCKED;
  const shown = figuresToShow(period);
  const wholeMonthAway = (period.absence_minutes ?? 0) + (period.holiday_minutes ?? 0);
  const soFarAway = (period.to_date?.absence_minutes ?? 0) + (period.to_date?.holiday_minutes ?? 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Figure
          label="Owed"
          value={formatMinutes(shown.target)}
          hint={
            shown.isPartial
              ? `${formatMinutes(shown.monthTarget)} for the whole month`
              : contractedWeeklyMinutes
                ? `${formatMinutes(contractedWeeklyMinutes)} a week`
                : undefined
          }
        />
        <Figure
          label="Worked"
          value={formatMinutes(shown.actual)}
          hint={
            (shown.isPartial ? soFarAway : wholeMonthAway)
              ? `includes ${formatMinutes(shown.isPartial ? soFarAway : wholeMonthAway)} away or on holiday`
              : undefined
          }
        />
        <Figure
          label="Balance"
          value={formatBalance(shown.balance)}
          tone={balanceTone(shown.balance)}
          hint={
            period.closing_balance_minutes !== null
              ? `${formatBalance(period.closing_balance_minutes)} carried forward`
              : undefined
          }
        />
      </div>

      <div className="text-xs text-custom-text-300 flex flex-wrap items-center gap-3">
        {shown.isPartial ? (
          <span className="text-custom-text-400">
            {shown.countedThrough
              ? `As things stand on ${formatDayLabel(shown.countedThrough)}. The month is not over.`
              : "This month has not started yet."}
          </span>
        ) : null}
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded px-2 py-0.5 font-medium",
            isFinal
              ? "bg-custom-background-80 text-custom-text-200"
              : "bg-custom-primary-100/10 text-custom-primary-100"
          )}
        >
          <Clock className="size-3" />
          {periodStateLabel(period.state)}
        </span>

        {hasRunningTimer ? (
          <span className="text-custom-text-300 inline-flex items-center gap-1">
            <Timer className="size-3" />A timer is still running, so this month cannot be handed in yet.
          </span>
        ) : null}

        {needsReview ? (
          <span className="text-amber-600 inline-flex items-center gap-1">
            <AlertTriangle className="size-3" />
            Some days need looking at — hours that were counted before are no longer there.
          </span>
        ) : null}
      </div>
    </div>
  );
};
