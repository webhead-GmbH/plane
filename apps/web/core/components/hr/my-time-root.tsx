/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Link, useParams } from "react-router";
import { ChevronLeft, ChevronRight, RefreshCw, Send, Users } from "lucide-react";
import useSWR from "swr";
// plane imports
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
// local imports
import { EHrPeriodState, HrService } from "@/services/hr.service";
import { HrDayTable } from "./day-table";
import { HrMonthSummary } from "./month-summary";
import { formatMonthLabel, isPeriodEditable, nextMonth, previousMonth } from "./utils";

const hrService = new HrService();

export const MyTimeRoot = observer(function MyTimeRoot() {
  // Only used to build the link, not to decide what the figures are.
  const { workspaceSlug } = useParams();
  const now = new Date();
  const [[year, month], setMonth] = useState<[number, number]>([now.getFullYear(), now.getMonth() + 1]);
  const [isBusy, setIsBusy] = useState(false);

  const { data, isLoading, mutate } = useSWR(`HR_ME_${year}_${month}`, () => hrService.me(year, month));

  const period = data?.period ?? null;
  const days = period?.days ?? [];
  const monthLabel = formatMonthLabel(`${year}-${String(month).padStart(2, "0")}-01`);

  const handleRecompute = async () => {
    if (!period) return;
    setIsBusy(true);
    try {
      await hrService.recompute(period.id);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Brought up to date" });
    } catch (error) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Could not bring it up to date",
        message: (error as { error?: string })?.error ?? "Try again in a moment.",
      });
    } finally {
      setIsBusy(false);
    }
  };

  const handleSubmit = async () => {
    if (!period) return;
    setIsBusy(true);
    try {
      await hrService.submit(period.id);
      await mutate();
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Handed in",
        message: `${monthLabel} has gone for approval.`,
      });
    } catch (error) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Not handed in",
        message: (error as { error?: string })?.error ?? "Try again in a moment.",
      });
    } finally {
      setIsBusy(false);
    }
  };

  if (isLoading)
    return (
      <Loader className="flex flex-col gap-3 p-4">
        <Loader.Item height="96px" />
        <Loader.Item height="40px" />
        <Loader.Item height="320px" />
      </Loader>
    );

  // Somebody can be a member of the workspace without being employed through it —
  // an administrator, or a guest on one project. There is nothing to show them,
  // and saying so is better than an empty table.
  if (!data?.profile)
    return (
      <div className="p-4">
        <div className="border-custom-border-200 bg-custom-background-90 rounded-md border px-4 py-6">
          <p className="text-sm text-custom-text-200 font-medium">No employment record here</p>
          <p className="text-sm text-custom-text-300 mt-1">
            Your hours are not being tracked in this workspace. If they should be, ask whoever looks after the team to
            set you up.
          </p>
        </div>
      </div>
    );

  // A month still running cannot be handed in — the server refuses it, because a
  // submitted month stops being rebuilt and hours logged afterwards would never
  // be counted. Saying so on the button beats letting it fail on every press.
  const monthIsRunning = !!period?.to_date;
  const canHandIn = period && isPeriodEditable(period.state) && !data.has_running_timer && !monthIsRunning;

  return (
    <div className="flex flex-col gap-5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMonth(previousMonth(year, month))}
            aria-label="Previous month"
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-sm text-custom-text-100 min-w-[10rem] text-center font-medium">{monthLabel}</span>
          <Button variant="ghost" size="sm" onClick={() => setMonth(nextMonth(year, month))} aria-label="Next month">
            <ChevronRight className="size-4" />
          </Button>
        </div>

        <div className="flex items-center gap-2">
          {data.is_hr_manager ? (
            <Link to={`/${workspaceSlug}/team-time`}>
              <Button variant="secondary" size="sm">
                <Users className="size-3.5" />
                Everyone
              </Button>
            </Link>
          ) : null}
          {period && isPeriodEditable(period.state) ? (
            <Button variant="secondary" size="sm" onClick={handleRecompute} loading={isBusy}>
              <RefreshCw className="size-3.5" />
              Bring up to date
            </Button>
          ) : null}
          {period && period.state !== EHrPeriodState.LOCKED ? (
            <Button
              variant="primary"
              size="sm"
              onClick={handleSubmit}
              disabled={!canHandIn}
              loading={isBusy}
              title={
                monthIsRunning
                  ? "The month is not over yet. It can be handed in once it has ended."
                  : data.has_running_timer
                    ? "Stop the timer that is still running, then hand the month in."
                    : undefined
              }
            >
              <Send className="size-3.5" />
              Hand in
            </Button>
          ) : null}
        </div>
      </div>

      <HrMonthSummary
        period={period}
        hasRunningTimer={data.has_running_timer}
        contractedWeeklyMinutes={data.schedule?.weekly_minutes ?? data.contract?.weekly_minutes ?? null}
      />

      <HrDayTable days={days} countedThrough={period?.to_date ? period.to_date.counted_through : undefined} />
    </div>
  );
});
