/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AlertTriangle, Timer } from "lucide-react";
// plane imports
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { Button } from "@plane/propel/button";
import { useTranslation } from "@plane/i18n";

import { cn } from "@plane/utils";
// local imports
import { EHrPeriodState, type THrOverviewRow } from "@/services/hr.service";
import { balanceTone, figuresToShow, formatBalance, formatMinutes, periodStateKey } from "./utils";

type TProps = {
  rows: THrOverviewRow[];
  busyPeriodId: string | null;
  onApprove: (row: THrOverviewRow) => void;
  onLock: (row: THrOverviewRow) => void;
  onReopen: (row: THrOverviewRow) => void;
  onReview: (row: THrOverviewRow) => void;
};

const StateChip = ({ state }: { state: EHrPeriodState }) => {
  const { t } = useTranslation();
  return (
    <span
      className={cn(
        "inline-flex rounded px-2 py-0.5 text-13 font-medium whitespace-nowrap",
        state === EHrPeriodState.LOCKED
          ? "bg-layer-2 text-secondary"
          : state === EHrPeriodState.APPROVED
            ? "bg-success-subtle text-success-primary"
            : state === EHrPeriodState.SUBMITTED
              ? "bg-accent-primary/10 text-accent-primary"
              : "bg-layer-1 text-tertiary"
      )}
    >
      {t(periodStateKey(state))}
    </span>
  );
};

/**
 * Everybody's month, one row each.
 *
 * The decimal hours sit next to the hours-and-minutes because those are the two
 * numbers that get copied out of here — one into a conversation, the other into
 * the payroll sheet — and having to convert between them by hand is how a figure
 * ends up transcribed wrong.
 */
export const HrOverviewTable = ({ rows, busyPeriodId, onApprove, onLock, onReopen, onReview }: TProps) => {
  const { t } = useTranslation();

  if (rows.length === 0)
    return (
      <div className="rounded-md border border-subtle bg-layer-1 px-4 py-6 text-13 text-tertiary">
        {t("hr.overview_table.nobody_yet")}
      </div>
    );

  // A month that has not ended cannot be handed in, so nobody is being waited on.
  const today = new Date().toISOString().slice(0, 10);
  const monthStillRunning = rows.length > 0 && rows[0].period_end >= today;

  return (
    <div className="overflow-x-auto rounded-md border border-subtle">
      <table className="w-full min-w-[54rem] text-13">
        <thead className="border-b border-subtle text-13 text-placeholder">
          <tr>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.overview_table.person")}</th>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.overview_table.state")}</th>
            <th className="px-4 py-2.5 text-right font-medium">{t("hr.overview_table.owed")}</th>
            <th className="px-4 py-2.5 text-right font-medium">{t("hr.overview_table.worked")}</th>
            <th className="px-4 py-2.5 text-right font-medium">{t("hr.overview_table.balance")}</th>
            <th className="px-4 py-2.5 text-right font-medium">{t("hr.overview_table.carried")}</th>
            <th className="px-4 py-2.5 text-right font-medium">{t("hr.overview_table.action")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isBusy = busyPeriodId === row.id;
            // The same choice the roll-up above makes, so the header is the sum
            // of the column under it rather than a different question's answer.
            const shown = figuresToShow(row);
            return (
              <tr key={row.id} className="border-t border-subtle hover:bg-layer-1/60">
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-primary">{row.member_display_name}</span>
                    {row.has_running_timer ? (
                      <Tooltip label={t("hr.overview_table.timer_running")} side="top">
                        <Timer className="size-3.5 text-tertiary" aria-label={t("hr.overview_table.timer_running")} />
                      </Tooltip>
                    ) : null}
                    {row.needs_review ? (
                      <Tooltip label={t("hr.overview_table.needs_review")} side="top">
                        {/* A button rather than an icon: the flag is the one thing
                            on this row somebody has to act on, and pointing at it
                            without offering the action left the month stuck. */}
                        <button
                          type="button"
                          onClick={() => onReview(row)}
                          aria-label={t("hr.overview_table.needs_review")}
                          className="text-warning-primary hover:text-warning-primary/80"
                        >
                          <AlertTriangle className="size-3.5" />
                        </button>
                      </Tooltip>
                    ) : null}
                  </div>
                </td>
                <td className="px-4 py-2">
                  <StateChip state={row.state} />
                </td>
                <td
                  className="px-4 py-2 text-right text-secondary tabular-nums"
                  title={
                    shown.isPartial
                      ? t("hr.summary.whole_month", { duration: formatMinutes(shown.monthTarget) })
                      : undefined
                  }
                >
                  {formatMinutes(shown.target)}
                </td>
                <td className="px-4 py-2 text-right text-primary tabular-nums">{formatMinutes(shown.actual)}</td>
                <td className={cn("px-4 py-2 text-right font-medium tabular-nums", balanceTone(shown.balance))}>
                  {formatBalance(shown.balance)}
                </td>
                <td className="px-4 py-2 text-right text-tertiary tabular-nums">
                  {formatBalance(row.closing_balance_minutes)}
                </td>
                <td className="px-4 py-2 text-right">
                  {/* The flagged days are offered ahead of an agreed month,
                      because closing is refused while any day is flagged and a
                      Close button there can only fail. Handing a month in and
                      reopening one are not blocked by a flag, so those two keep
                      their own action. */}
                  {row.state === EHrPeriodState.SUBMITTED ? (
                    <Button variant="primary" size="lg" loading={isBusy} onClick={() => onApprove(row)}>
                      {t("hr.overview_table.agree")}
                    </Button>
                  ) : row.state === EHrPeriodState.LOCKED ? (
                    <Button variant="link" size="lg" loading={isBusy} onClick={() => onReopen(row)}>
                      {t("hr.overview_table.reopen")}
                    </Button>
                  ) : row.needs_review ? (
                    <Button variant="secondary" size="lg" prependIcon={<AlertTriangle />} onClick={() => onReview(row)}>
                      {t("hr.overview_table.blocked_by_review")}
                    </Button>
                  ) : row.state === EHrPeriodState.APPROVED ? (
                    <Button variant="primary" size="lg" loading={isBusy} onClick={() => onLock(row)}>
                      {t("hr.overview_table.close")}
                    </Button>
                  ) : (
                    <span className="text-13 text-tertiary">
                      {monthStillRunning
                        ? t("hr.overview_table.month_running")
                        : t("hr.overview_table.waiting_for", { person: row.member_display_name })}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
