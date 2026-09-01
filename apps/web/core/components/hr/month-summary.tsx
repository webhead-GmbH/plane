/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AlertTriangle, Clock, Timer } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// local imports
import { EHrPeriodState, type THrPeriod } from "@/services/hr.service";
import { balanceTone, figuresToShow, formatBalance, formatDayLabel, formatMinutes, periodStateKey } from "./utils";

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
  const { t, currentLocale } = useTranslation();
  const shown = figuresToShow(period);
  const wholeMonthAway = (period.absence_minutes ?? 0) + (period.holiday_minutes ?? 0);
  const soFarAway = (period.to_date?.absence_minutes ?? 0) + (period.to_date?.holiday_minutes ?? 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Figure
          label={t("hr.summary.owed")}
          value={formatMinutes(shown.target)}
          hint={
            shown.isPartial
              ? t("hr.summary.whole_month", { duration: formatMinutes(shown.monthTarget) })
              : contractedWeeklyMinutes
                ? t("hr.summary.per_week", { duration: formatMinutes(contractedWeeklyMinutes) })
                : undefined
          }
        />
        <Figure
          label={t("hr.summary.worked")}
          value={formatMinutes(shown.actual)}
          hint={
            (shown.isPartial ? soFarAway : wholeMonthAway)
              ? t("hr.summary.includes_away", {
                  duration: formatMinutes(shown.isPartial ? soFarAway : wholeMonthAway),
                })
              : undefined
          }
        />
        <Figure
          label={t("hr.summary.balance")}
          value={formatBalance(shown.balance)}
          tone={balanceTone(shown.balance)}
          hint={
            period.closing_balance_minutes !== null
              ? t("hr.summary.carried_forward", { duration: formatBalance(period.closing_balance_minutes) })
              : undefined
          }
        />
      </div>

      <div className="text-xs text-custom-text-300 flex flex-wrap items-center gap-3">
        {shown.isPartial ? (
          <span className="text-custom-text-400">
            {shown.countedThrough
              ? t("hr.summary.as_of", { date: formatDayLabel(shown.countedThrough, currentLocale) })
              : t("hr.summary.not_started")}
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
          {t(periodStateKey(period.state))}
        </span>

        {hasRunningTimer ? (
          <span className="text-custom-text-300 inline-flex items-center gap-1">
            <Timer className="size-3" />
            {t("hr.summary.timer_running")}
          </span>
        ) : null}

        {needsReview ? (
          <span className="text-amber-600 inline-flex items-center gap-1">
            <AlertTriangle className="size-3" />
            {t("hr.summary.needs_review")}
          </span>
        ) : null}
      </div>
    </div>
  );
};
