/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AlertTriangle, Timer } from "lucide-react";
// plane imports
import { Button } from "@plane/propel/button";
import { cn } from "@plane/utils";
// local imports
import { EHrPeriodState, type THrOverviewRow } from "@/services/hr.service";
import { balanceTone, formatBalance, formatDecimalHours, formatMinutes, periodStateLabel } from "./utils";

type TProps = {
  rows: THrOverviewRow[];
  busyPeriodId: string | null;
  onApprove: (row: THrOverviewRow) => void;
  onLock: (row: THrOverviewRow) => void;
  onReopen: (row: THrOverviewRow) => void;
};

const StateChip = ({ state }: { state: EHrPeriodState }) => (
  <span
    className={cn(
      "text-xs inline-flex rounded px-2 py-0.5 font-medium whitespace-nowrap",
      state === EHrPeriodState.LOCKED
        ? "bg-custom-background-80 text-custom-text-200"
        : state === EHrPeriodState.APPROVED
          ? "bg-green-500/10 text-green-600"
          : state === EHrPeriodState.SUBMITTED
            ? "bg-custom-primary-100/10 text-custom-primary-100"
            : "bg-custom-background-90 text-custom-text-300"
    )}
  >
    {periodStateLabel(state)}
  </span>
);

/**
 * Everybody's month, one row each.
 *
 * The decimal hours sit next to the hours-and-minutes because those are the two
 * numbers that get copied out of here — one into a conversation, the other into
 * the payroll sheet — and having to convert between them by hand is how a figure
 * ends up transcribed wrong.
 */
export const HrOverviewTable = ({ rows, busyPeriodId, onApprove, onLock, onReopen }: TProps) => {
  if (rows.length === 0)
    return (
      <div className="border-custom-border-200 bg-custom-background-90 text-sm text-custom-text-300 rounded-md border px-4 py-6">
        Nobody has an employment record yet.
      </div>
    );

  return (
    <div className="border-custom-border-200 overflow-x-auto rounded-md border">
      <table className="text-sm w-full min-w-[54rem]">
        <thead className="bg-custom-background-90 text-custom-text-400 text-xs tracking-wide uppercase">
          <tr>
            <th className="px-4 py-2 text-left font-medium">Person</th>
            <th className="px-4 py-2 text-left font-medium">State</th>
            <th className="px-4 py-2 text-right font-medium">Owed</th>
            <th className="px-4 py-2 text-right font-medium">Worked</th>
            <th className="px-4 py-2 text-right font-medium">Hours</th>
            <th className="px-4 py-2 text-right font-medium">Balance</th>
            <th className="px-4 py-2 text-right font-medium">Carried</th>
            <th className="px-4 py-2 text-right font-medium">Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isBusy = busyPeriodId === row.id;
            return (
              <tr key={row.id} className="border-custom-border-200 hover:bg-custom-background-90/60 border-t">
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2">
                    <span className="text-custom-text-100 font-medium">{row.member_display_name}</span>
                    {row.has_running_timer ? (
                      <Timer className="text-custom-text-400 size-3.5" aria-label="A timer is still running" />
                    ) : null}
                    {row.needs_review ? (
                      <AlertTriangle className="text-amber-600 size-3.5" aria-label="Some days need looking at" />
                    ) : null}
                  </div>
                </td>
                <td className="px-4 py-2">
                  <StateChip state={row.state} />
                </td>
                <td className="text-custom-text-200 px-4 py-2 text-right tabular-nums">
                  {formatMinutes(row.target_minutes)}
                </td>
                <td className="text-custom-text-100 px-4 py-2 text-right tabular-nums">
                  {formatMinutes(row.actual_minutes)}
                </td>
                <td className="text-custom-text-300 px-4 py-2 text-right tabular-nums">
                  {formatDecimalHours(row.actual_minutes)}
                </td>
                <td className={cn("px-4 py-2 text-right font-medium tabular-nums", balanceTone(row.balance_minutes))}>
                  {formatBalance(row.balance_minutes)}
                </td>
                <td className="text-custom-text-300 px-4 py-2 text-right tabular-nums">
                  {formatBalance(row.closing_balance_minutes)}
                </td>
                <td className="px-4 py-2 text-right">
                  {row.state === EHrPeriodState.SUBMITTED ? (
                    <Button variant="primary" size="sm" loading={isBusy} onClick={() => onApprove(row)}>
                      Agree
                    </Button>
                  ) : row.state === EHrPeriodState.APPROVED ? (
                    <Button variant="primary" size="sm" loading={isBusy} onClick={() => onLock(row)}>
                      Close
                    </Button>
                  ) : row.state === EHrPeriodState.LOCKED ? (
                    <Button variant="link" size="sm" loading={isBusy} onClick={() => onReopen(row)}>
                      Reopen
                    </Button>
                  ) : (
                    <span className="text-custom-text-400 text-xs">Not handed in</span>
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
