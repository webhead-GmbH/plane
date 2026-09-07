/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, Pencil } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// local imports
import { EHrDayKind, type THrPeriodDay } from "@/services/hr.service";
import { balanceTone, dayKindKey, formatBalance, formatDayLabel, formatMinutes, hasHappened, isToday } from "./utils";

type TProps = {
  days: THrPeriodDay[];
  /**
   * How far into the month the figures reach, or null for a month that has not
   * started. Absent entirely for a month that is over, which is why it is
   * optional rather than nullable — a finished month must not read as one where
   * nothing has happened.
   */
  countedThrough?: string | null;
  /** Opens a day for editing. Absent when the month cannot be changed. */
  onPickDay?: (workDate: string) => void;
};

const QUIET_KINDS = new Set([EHrDayKind.NON_WORKING, EHrDayKind.HOLIDAY, EHrDayKind.HALF_HOLIDAY]);

/**
 * The month day by day.
 *
 * Days nobody was expected to work are dimmed rather than hidden. Leaving them out
 * would make the list shorter, but somebody scanning for where their hours went
 * needs to see that a gap was a Saturday and not a day they forgot.
 */
export const HrDayTable = ({ days, countedThrough, onPickDay }: TProps) => {
  const { t, currentLocale } = useTranslation();
  const [showToCome, setShowToCome] = useState(false);

  if (!days.length)
    return (
      <div className="rounded-md border border-subtle px-4 py-6 text-13 text-tertiary">
        {t("hr.day_table.nothing_yet")}
      </div>
    );

  const stillToCome = (day: THrPeriodDay) =>
    countedThrough !== undefined && !hasHappened(day.work_date, countedThrough);
  const toCome = days.filter(stillToCome);
  const shown = showToCome ? days : days.filter((day) => !stillToCome(day));

  return (
    <div className="overflow-x-auto rounded-md border border-subtle">
      <table className="w-full min-w-[42rem] text-13">
        <thead>
          <tr className="border-b border-subtle text-left">
            <th className="px-3 py-2.5 text-13 font-medium text-placeholder">{t("hr.day_table.day")}</th>
            <th className="px-3 py-2.5 text-13 font-medium text-placeholder">{t("hr.day_table.what_it_was")}</th>
            <th className="px-3 py-2.5 text-right text-13 font-medium text-placeholder">{t("hr.day_table.owed")}</th>
            <th className="px-3 py-2.5 text-right text-13 font-medium text-placeholder">
              {t("hr.day_table.work_items")}
            </th>
            <th className="px-3 py-2.5 text-right text-13 font-medium text-placeholder">{t("hr.day_table.other")}</th>
            <th className="px-3 py-2.5 text-right text-13 font-medium text-placeholder">{t("hr.day_table.away")}</th>
            <th className="px-3 py-2.5 text-right text-13 font-medium text-placeholder">{t("hr.day_table.worked")}</th>
            <th className="px-3 py-2.5 text-right text-13 font-medium text-placeholder">{t("hr.day_table.balance")}</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((day) => {
            const quiet = QUIET_KINDS.has(day.day_kind) && !day.actual_minutes;
            const away = day.absence_minutes + day.holiday_minutes;
            // Only a month still in flight has days that have not happened. When
            // the prop is absent the month is over and every day counts.
            const notYet = stillToCome(day);
            return (
              <tr
                key={day.id}
                className={cn(
                  onPickDay && "group/row hover:bg-layer-2",
                  "border-b border-subtle last:border-b-0",
                  quiet && "bg-layer-1/40 text-tertiary",
                  notYet && "text-tertiary opacity-60",
                  isToday(day.work_date) && "bg-accent-primary/5"
                )}
              >
                <td className="px-3 py-1.5 whitespace-nowrap">
                  {onPickDay ? (
                    <button
                      type="button"
                      onClick={() => onPickDay(day.work_date)}
                      aria-label={t("hr.day_table.open_day", {
                        day: formatDayLabel(day.work_date, currentLocale),
                      })}
                      className={cn(
                        "group/day inline-flex items-center gap-1.5 rounded-sm focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none",
                        isToday(day.work_date) && "font-medium text-accent-primary"
                      )}
                    >
                      {formatDayLabel(day.work_date, currentLocale)}
                      <Pencil className="size-3 opacity-0 transition-opacity group-hover/row:opacity-60" />
                    </button>
                  ) : (
                    <span className={cn(isToday(day.work_date) && "font-medium text-accent-primary")}>
                      {formatDayLabel(day.work_date, currentLocale)}
                    </span>
                  )}
                </td>
                <td className="px-3 py-1.5 text-tertiary">
                  <span className="inline-flex items-center gap-1.5">
                    {t(dayKindKey(day.day_kind))}
                    {day.needs_review ? (
                      <AlertTriangle
                        className="size-3.5 text-warning-primary"
                        aria-label={t("hr.day_table.needs_review")}
                      />
                    ) : null}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatMinutes(day.target_minutes)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatMinutes(day.project_minutes)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatMinutes(day.non_project_minutes)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatMinutes(away)}</td>
                <td className="px-3 py-1.5 text-right font-medium tabular-nums">{formatMinutes(day.actual_minutes)}</td>
                <td
                  className={cn(
                    "px-3 py-1.5 text-right tabular-nums",
                    notYet ? "text-tertiary" : balanceTone(day.balance_minutes)
                  )}
                  title={notYet ? t("hr.day_table.not_yet") : undefined}
                >
                  {notYet ? "—" : formatBalance(day.balance_minutes)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {toCome.length > 0 ? (
        <button
          type="button"
          onClick={() => setShowToCome((open) => !open)}
          className="flex w-full items-center justify-center gap-1.5 border-t border-subtle px-3 py-2.5 text-13 text-tertiary transition-colors hover:bg-layer-2 hover:text-primary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
        >
          {showToCome ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          {showToCome
            ? t("hr.day_table.hide_rest_of_month")
            : t("hr.day_table.rest_of_month", { count: toCome.length })}
        </button>
      ) : null}
    </div>
  );
};
