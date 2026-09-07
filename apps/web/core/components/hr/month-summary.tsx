/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AlertTriangle, Clock, House, Palmtree, Timer } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// local imports
import { EHrPeriodState, type THrLeaveStanding, type THrWorkSchedule } from "@/services/hr.service";
import { type THrPeriod } from "@/services/hr.service";
import {
  balanceTone,
  figuresToShow,
  formatBalance,
  formatDayLabel,
  formatMinutes,
  inDays,
  periodStateKey,
} from "./utils";
import { HrFigure } from "./figure";

type TProps = {
  period: THrPeriod | null;
  hasRunningTimer: boolean;
  contractedWeeklyMinutes?: number | null;
  /** Days worked from home so far this calendar year. Null where none are kept. */
  teleworkDaysThisYear?: number | null;
  /** What is left of this leave year. Null where no leave account is kept. */
  leave?: THrLeaveStanding | null;
  /** Only to say what a day is worth, so leave can be shown in days. */
  schedule?: THrWorkSchedule | null;
};

/**
 * The three figures the month comes down to, kept above everything else.
 *
 * A shortfall is only worth showing if it is seen while there is still time to do
 * something about it, so the balance is given the same weight as the hours and is
 * not tucked into a total at the bottom of a table.
 */
export const HrMonthSummary = ({
  period,
  hasRunningTimer,
  contractedWeeklyMinutes,
  teleworkDaysThisYear,
  leave,
  schedule,
}: TProps) => {
  // Before the early return: a hook that runs only sometimes breaks the moment
  // this month goes from nothing to something, which is the ordinary case.
  const { t, currentLocale } = useTranslation();

  if (!period)
    return (
      <div className="rounded-md border border-subtle bg-layer-1 px-4 py-6 text-13 text-tertiary">
        {t("hr.summary.nothing_yet")}
      </div>
    );

  const needsReview = (period.days ?? []).some((day) => day.needs_review);
  const isFinal = period.state === EHrPeriodState.LOCKED;
  // Leave is the one figure people think about in days rather than hours, so it
  // is shown that way wherever the schedule says what a day is worth. The unit
  // is named either way: "8.4" on its own was a number nobody could act on.
  const leaveInDays = leave ? inDays(leave.remaining_minutes, schedule) : null;
  const leaveLeft = leave
    ? leaveInDays !== null
      ? t("hr.summary.leave_left_days", { amount: leaveInDays })
      : t("hr.summary.leave_left_hours", { amount: formatMinutes(leave.remaining_minutes) })
    : null;
  const shown = figuresToShow(period);
  const wholeMonthAway = (period.absence_minutes ?? 0) + (period.holiday_minutes ?? 0);
  const soFarAway = (period.to_date?.absence_minutes ?? 0) + (period.to_date?.holiday_minutes ?? 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <HrFigure
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
        <HrFigure
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
        <HrFigure
          label={t("hr.summary.balance")}
          value={formatBalance(shown.balance)}
          tone={balanceTone(shown.balance)}
          accent={
            // A balance nobody has worked out yet is not a shortfall.
            (shown.balance ?? 0) < 0 ? "border-danger-strong/40 bg-danger-subtle" : "border-subtle bg-layer-1"
          }
          hint={
            period.closing_balance_minutes !== null
              ? t("hr.summary.carried_forward", { duration: formatBalance(period.closing_balance_minutes) })
              : shown.balance
                ? t(shown.balance < 0 ? "hr.summary.behind_so_far" : "hr.summary.ahead_so_far", {
                    duration: formatMinutes(Math.abs(shown.balance)),
                  })
                : undefined
          }
        />
      </div>

      <div className="flex flex-wrap items-center gap-3 text-13 text-tertiary">
        {shown.isPartial ? (
          <span className="text-tertiary">
            {shown.countedThrough
              ? t("hr.summary.as_of", { date: formatDayLabel(shown.countedThrough, currentLocale) })
              : t("hr.summary.not_started")}
          </span>
        ) : null}
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded px-2 py-0.5 font-medium",
            isFinal ? "bg-layer-2 text-secondary" : "bg-accent-primary/10 text-accent-primary"
          )}
        >
          <Clock className="size-3" />
          {t(periodStateKey(period.state))}
        </span>

        {hasRunningTimer ? (
          <span className="inline-flex items-center gap-1 text-tertiary">
            <Timer className="size-3" />
            {t("hr.summary.timer_running")}
          </span>
        ) : null}

        {leaveLeft !== null ? (
          <span className="inline-flex items-center gap-1 text-tertiary">
            <Palmtree className="size-3" />
            {leaveLeft}
          </span>
        ) : null}

        {/* The year's figure, not the month's: it is reported per calendar year
            and is what somebody actually needs to know before booking another. */}
        {teleworkDaysThisYear ? (
          <span className="inline-flex items-center gap-1 text-tertiary">
            <House className="size-3" />
            {t("hr.summary.telework_days", { count: teleworkDaysThisYear })}
          </span>
        ) : null}

        {needsReview ? (
          <span className="inline-flex items-center gap-1 text-warning-primary">
            <AlertTriangle className="size-3" />
            {t("hr.summary.needs_review")}
          </span>
        ) : null}
      </div>
    </div>
  );
};
