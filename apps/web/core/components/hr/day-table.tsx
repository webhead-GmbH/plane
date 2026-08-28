/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AlertTriangle } from "lucide-react";
// plane imports
import { cn } from "@plane/utils";
// local imports
import { EHrDayKind, type THrPeriodDay } from "@/services/hr.service";
import { balanceTone, dayKindLabel, formatBalance, formatDayLabel, formatMinutes, isToday } from "./utils";

type TProps = {
  days: THrPeriodDay[];
};

const QUIET_KINDS = new Set([EHrDayKind.NON_WORKING, EHrDayKind.HOLIDAY, EHrDayKind.HALF_HOLIDAY]);

/**
 * The month day by day.
 *
 * Days nobody was expected to work are dimmed rather than hidden. Leaving them out
 * would make the list shorter, but somebody scanning for where their hours went
 * needs to see that a gap was a Saturday and not a day they forgot.
 */
export const HrDayTable = ({ days }: TProps) => {
  if (!days.length)
    return (
      <div className="border-custom-border-200 text-sm text-custom-text-300 rounded-md border px-4 py-6">
        No days have been worked out for this month yet.
      </div>
    );

  return (
    <div className="border-custom-border-200 overflow-x-auto rounded-md border">
      <table className="text-sm w-full min-w-[42rem]">
        <thead>
          <tr className="border-custom-border-200 bg-custom-background-90 border-b text-left">
            <th className="text-xs text-custom-text-400 px-3 py-2 font-medium tracking-wide uppercase">Day</th>
            <th className="text-xs text-custom-text-400 px-3 py-2 font-medium tracking-wide uppercase">What it was</th>
            <th className="text-xs text-custom-text-400 px-3 py-2 text-right font-medium tracking-wide uppercase">
              Owed
            </th>
            <th className="text-xs text-custom-text-400 px-3 py-2 text-right font-medium tracking-wide uppercase">
              Work items
            </th>
            <th className="text-xs text-custom-text-400 px-3 py-2 text-right font-medium tracking-wide uppercase">
              Other
            </th>
            <th className="text-xs text-custom-text-400 px-3 py-2 text-right font-medium tracking-wide uppercase">
              Away
            </th>
            <th className="text-xs text-custom-text-400 px-3 py-2 text-right font-medium tracking-wide uppercase">
              Worked
            </th>
            <th className="text-xs text-custom-text-400 px-3 py-2 text-right font-medium tracking-wide uppercase">
              Balance
            </th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => {
            const quiet = QUIET_KINDS.has(day.day_kind) && !day.actual_minutes;
            const away = day.absence_minutes + day.holiday_minutes;
            return (
              <tr
                key={day.id}
                className={cn(
                  "border-custom-border-100 border-b last:border-b-0",
                  quiet && "bg-custom-background-90/40 text-custom-text-400",
                  isToday(day.work_date) && "bg-custom-primary-100/5"
                )}
              >
                <td className="px-3 py-1.5 whitespace-nowrap">
                  <span className={cn(isToday(day.work_date) && "text-custom-primary-100 font-medium")}>
                    {formatDayLabel(day.work_date)}
                  </span>
                </td>
                <td className="text-custom-text-300 px-3 py-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    {dayKindLabel(day.day_kind)}
                    {day.needs_review ? (
                      <AlertTriangle
                        className="text-amber-600 size-3.5"
                        aria-label="Hours counted here earlier are no longer there"
                      />
                    ) : null}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatMinutes(day.target_minutes)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatMinutes(day.project_minutes)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatMinutes(day.non_project_minutes)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{away ? formatMinutes(away) : "—"}</td>
                <td className="px-3 py-1.5 text-right font-medium tabular-nums">{formatMinutes(day.actual_minutes)}</td>
                <td className={cn("px-3 py-1.5 text-right tabular-nums", balanceTone(day.balance_minutes))}>
                  {formatBalance(day.balance_minutes)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
