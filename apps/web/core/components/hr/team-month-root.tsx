/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { ChevronLeft, ChevronRight, Download } from "lucide-react";
import useSWR from "swr";
// plane imports
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
// local imports
import { EHrPeriodState, HrService, type THrOverviewRow } from "@/services/hr.service";
import { HrOverviewTable } from "./overview-table";
import { balanceTone, formatBalance, formatMinutes, formatMonthLabel, nextMonth, previousMonth } from "./utils";

const hrService = new HrService();

/**
 * The month for everybody, and the place it gets closed.
 *
 * Not tied to a workspace, because the people are the same people wherever they
 * are working — the same reason the personal view is not. A manager opens this
 * from whichever workspace they happen to be in and sees the whole company.
 */
export const HrTeamMonthRoot = observer(function HrTeamMonthRoot() {
  const now = new Date();
  const [[year, month], setMonth] = useState<[number, number]>([now.getFullYear(), now.getMonth() + 1]);
  const [busyPeriodId, setBusyPeriodId] = useState<string | null>(null);

  const { data, isLoading, error, mutate } = useSWR(`HR_OVERVIEW_${year}_${month}`, () =>
    hrService.overview(year, month)
  );

  const rows = data?.rows ?? [];
  const monthLabel = formatMonthLabel(`${year}-${String(month).padStart(2, "0")}-01`);

  const owed = rows.reduce((total, row) => total + (row.target_minutes ?? 0), 0);
  const worked = rows.reduce((total, row) => total + (row.actual_minutes ?? 0), 0);
  const balance = rows.reduce((total, row) => total + (row.balance_minutes ?? 0), 0);
  const outstanding = rows.filter((row) => row.state !== EHrPeriodState.LOCKED).length;

  const act = async (row: THrOverviewRow, work: () => Promise<unknown>, done: string) => {
    setBusyPeriodId(row.id);
    try {
      await work();
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: done });
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "That did not go through",
        message: (failure as { error?: string })?.error ?? "Please try again.",
      });
    } finally {
      setBusyPeriodId(null);
    }
  };

  const handleReopen = (row: THrOverviewRow) => {
    // A closed month is evidence, so putting one back into play has to say why.
    // The reason is kept with the month rather than only in an audit trail.
    const reason = window.prompt(`Why is ${row.member_display_name}'s ${monthLabel} being reopened?`);
    if (!reason?.trim()) return;
    void act(row, () => hrService.reopen(row.id, reason.trim()), "Reopened");
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-6 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            prependIcon={<ChevronLeft className="size-4" />}
            onClick={() => setMonth(previousMonth(year, month))}
          >
            Earlier
          </Button>
          <h1 className="text-custom-text-100 text-lg min-w-44 text-center font-semibold">{monthLabel}</h1>
          <Button
            variant="secondary"
            size="sm"
            appendIcon={<ChevronRight className="size-4" />}
            onClick={() => setMonth(nextMonth(year, month))}
          >
            Later
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <a href={hrService.monthExportUrl(year, month, "csv")} download>
            <Button variant="secondary" size="sm" prependIcon={<Download className="size-4" />}>
              CSV
            </Button>
          </a>
          <a href={hrService.monthExportUrl(year, month, "xlsx")} download>
            <Button variant="secondary" size="sm" prependIcon={<Download className="size-4" />}>
              Excel
            </Button>
          </a>
        </div>
      </div>

      {isLoading ? (
        <Loader className="flex flex-col gap-3">
          <Loader.Item height="72px" />
          <Loader.Item height="320px" />
        </Loader>
      ) : error ? (
        <div className="border-custom-border-200 bg-custom-background-90 rounded-md border px-4 py-6">
          <p className="text-custom-text-200 text-sm font-medium">This is not yours to see</p>
          <p className="text-custom-text-300 text-sm mt-1">
            Everyone&apos;s hours are only readable by whoever looks after the team. Your own month is on{" "}
            <span className="font-medium">My time</span>.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="border-custom-border-200 bg-custom-background-100 flex flex-col gap-0.5 rounded-md border px-4 py-3">
              <span className="text-custom-text-400 text-xs font-medium tracking-wide uppercase">Owed</span>
              <span className="text-custom-text-100 text-2xl font-semibold tabular-nums">{formatMinutes(owed)}</span>
            </div>
            <div className="border-custom-border-200 bg-custom-background-100 flex flex-col gap-0.5 rounded-md border px-4 py-3">
              <span className="text-custom-text-400 text-xs font-medium tracking-wide uppercase">Worked</span>
              <span className="text-custom-text-100 text-2xl font-semibold tabular-nums">{formatMinutes(worked)}</span>
            </div>
            <div className="border-custom-border-200 bg-custom-background-100 flex flex-col gap-0.5 rounded-md border px-4 py-3">
              <span className="text-custom-text-400 text-xs font-medium tracking-wide uppercase">Balance</span>
              <span className={`text-2xl font-semibold tabular-nums ${balanceTone(balance)}`}>
                {formatBalance(balance)}
              </span>
            </div>
            <div className="border-custom-border-200 bg-custom-background-100 flex flex-col gap-0.5 rounded-md border px-4 py-3">
              <span className="text-custom-text-400 text-xs font-medium tracking-wide uppercase">Still open</span>
              <span className="text-custom-text-100 text-2xl font-semibold tabular-nums">
                {outstanding} of {rows.length}
              </span>
            </div>
          </div>

          <HrOverviewTable
            rows={rows}
            busyPeriodId={busyPeriodId}
            onApprove={(row) => void act(row, () => hrService.approve(row.id), "Agreed")}
            onLock={(row) => void act(row, () => hrService.lock(row.id), "Closed")}
            onReopen={handleReopen}
          />

          <p className="text-custom-text-400 text-xs">
            Everyone&apos;s hours are counted wherever they logged them. Closing a month freezes its figures; nothing
            recorded afterwards changes them.
          </p>
        </>
      )}
    </div>
  );
});
