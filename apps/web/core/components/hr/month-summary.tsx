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

/** The month's figures, or as much of them as has been counted so far. */
type TFigures = ReturnType<typeof figuresToShow>;

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
  const { t } = useTranslation();

  if (!period)
    return (
      <div className="rounded-md border border-subtle bg-layer-1 px-4 py-6 text-13 text-tertiary">
        {t("hr.summary.nothing_yet")}
      </div>
    );

  const shown = figuresToShow(period);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <OwedFigure shown={shown} contractedWeeklyMinutes={contractedWeeklyMinutes} />
        <WorkedFigure period={period} shown={shown} />
        <BalanceFigure period={period} shown={shown} />
      </div>

      <MonthNotes
        period={period}
        shown={shown}
        hasRunningTimer={hasRunningTimer}
        teleworkDaysThisYear={teleworkDaysThisYear}
        leave={leave}
        schedule={schedule}
      />
    </div>
  );
};

/** What the contract asks for, against the whole month or against what has run of it. */
const OwedFigure = ({
  shown,
  contractedWeeklyMinutes,
}: {
  shown: TFigures;
  contractedWeeklyMinutes?: number | null;
}) => {
  const { t } = useTranslation();

  return (
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
  );
};

/** Absence and holidays, over the whole month or over as much of it as has been counted. */
const awayMinutes = (period: THrPeriod, isPartial: boolean) =>
  isPartial
    ? (period.to_date?.absence_minutes ?? 0) + (period.to_date?.holiday_minutes ?? 0)
    : (period.absence_minutes ?? 0) + (period.holiday_minutes ?? 0);

/**
 * The hours that count as worked.
 *
 * Time away counts towards them, so the hint says how much of the figure is time
 * nobody was actually at their desk for.
 */
const WorkedFigure = ({ period, shown }: { period: THrPeriod; shown: TFigures }) => {
  const { t } = useTranslation();

  const away = awayMinutes(period, shown.isPartial);

  return (
    <HrFigure
      label={t("hr.summary.worked")}
      value={formatMinutes(shown.actual)}
      hint={away ? t("hr.summary.includes_away", { duration: formatMinutes(away) }) : undefined}
    />
  );
};

/** The figure the screen exists for, and what became of it once the month was closed. */
const BalanceFigure = ({ period, shown }: { period: THrPeriod; shown: TFigures }) => {
  const { t } = useTranslation();

  return (
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
  );
};

/** Where the month stands, and the things about it the three figures cannot say. */
const MonthNotes = ({
  period,
  shown,
  hasRunningTimer,
  teleworkDaysThisYear,
  leave,
  schedule,
}: {
  period: THrPeriod;
  shown: TFigures;
  hasRunningTimer: boolean;
  teleworkDaysThisYear?: number | null;
  leave?: THrLeaveStanding | null;
  schedule?: THrWorkSchedule | null;
}) => {
  const { t } = useTranslation();

  const needsReview = (period.days ?? []).some((day) => day.needs_review);

  return (
    <div className="flex flex-wrap items-center gap-3 text-13 text-tertiary">
      <CountedThroughNote shown={shown} />
      <PeriodStateBadge state={period.state} />

      {hasRunningTimer ? (
        <span className="inline-flex items-center gap-1 text-tertiary">
          <Timer className="size-3" />
          {t("hr.summary.timer_running")}
        </span>
      ) : null}

      <LeaveLeftNote leave={leave} schedule={schedule} />

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
  );
};

/** How far into a month still running the figures above have been counted. */
const CountedThroughNote = ({ shown }: { shown: TFigures }) => {
  const { t, currentLocale } = useTranslation();

  if (!shown.isPartial) return null;

  return (
    <span className="text-tertiary">
      {shown.countedThrough
        ? t("hr.summary.as_of", { date: formatDayLabel(shown.countedThrough, currentLocale) })
        : t("hr.summary.not_started")}
    </span>
  );
};

/** The state of the month, worn as accent until nothing about it can change any more. */
const PeriodStateBadge = ({ state }: { state: EHrPeriodState }) => {
  const { t } = useTranslation();

  const isFinal = state === EHrPeriodState.LOCKED;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-2 py-0.5 font-medium",
        isFinal ? "bg-layer-2 text-secondary" : "bg-accent-primary/10 text-accent-primary"
      )}
    >
      <Clock className="size-3" />
      {t(periodStateKey(state))}
    </span>
  );
};

/**
 * What is left of this leave year.
 *
 * Leave is the one figure people think about in days rather than hours, so it is
 * shown that way wherever the schedule says what a day is worth. The unit is
 * named either way: "8.4" on its own was a number nobody could act on.
 */
const LeaveLeftNote = ({ leave, schedule }: { leave?: THrLeaveStanding | null; schedule?: THrWorkSchedule | null }) => {
  const { t } = useTranslation();

  if (!leave) return null;

  const days = inDays(leave.remaining_minutes, schedule);

  return (
    <span className="inline-flex items-center gap-1 text-tertiary">
      <Palmtree className="size-3" />
      {days !== null
        ? t("hr.summary.leave_left_days", { amount: days })
        : t("hr.summary.leave_left_hours", { amount: formatMinutes(leave.remaining_minutes) })}
    </span>
  );
};
