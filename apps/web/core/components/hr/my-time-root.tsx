/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useNavigate, useParams } from "react-router";
import { Download, ListTree, MoreHorizontal, Plus, RefreshCw, Scale, Send, Users } from "lucide-react";
import useSWR from "swr";
// plane imports
import { Button } from "@plane/propel/button";
import { useTranslation } from "@plane/i18n";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { CustomMenu, Loader, Tooltip } from "@plane/ui";
// local imports
import { EHrPeriodState, HrService } from "@/services/hr.service";
import { HrDayTable } from "./day-table";
import { HrDayEntriesModal } from "./day-entries-modal";
import { HrOpeningBalanceModal } from "./opening-balance-modal";
import { HrMonthSummary } from "./month-summary";
import { HrPeriodStepper } from "./period-stepper";
import { HrStatementPanel } from "./statement-panel";
import { formatMonthLabel, isPeriodEditable, nextMonth, previousMonth, refusalMessage } from "./utils";

const hrService = new HrService();

export const MyTimeRoot = observer(function MyTimeRoot() {
  // Only used to navigate, never to decide what the figures are: the month comes
  // from the server against the signed-in person, not from the address bar.
  const { workspaceSlug } = useParams();
  const navigate = useNavigate();
  const now = new Date();
  // Recording time is about today, so the button opens today rather than asking.
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const [[year, month], setMonth] = useState<[number, number]>([now.getFullYear(), now.getMonth() + 1]);
  const [isBusy, setIsBusy] = useState(false);
  const [openDay, setOpenDay] = useState<string | null>(null);
  const [showOpening, setShowOpening] = useState(false);

  const { t, currentLocale } = useTranslation();
  const { data, isLoading, error, mutate } = useSWR(`HR_ME_${year}_${month}`, () => hrService.me(year, month));

  const period = data?.period ?? null;
  const days = period?.days ?? [];
  // Only a day this month's period can answer for. Whether a day may be edited
  // is the period's answer, and the period on hand is the one being viewed — so
  // a day from any other month would be judged by the wrong month's state.
  const viewedMonth = `${year}-${String(month).padStart(2, "0")}`;
  const openDayInThisMonth = openDay && openDay.startsWith(viewedMonth) ? openDay : null;
  const monthLabel = formatMonthLabel(`${year}-${String(month).padStart(2, "0")}-01`, currentLocale);

  const handleRecompute = async () => {
    if (!period) return;
    setIsBusy(true);
    try {
      await hrService.recompute(period.id);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.my_time.toasts.recomputed") });
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("hr.my_time.toasts.not_recomputed"),
        message: refusalMessage(failure, t, currentLocale) ?? t("hr.my_time.toasts.try_again"),
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
        title: t("hr.my_time.toasts.handed_in"),
        message: t("hr.my_time.toasts.handed_in_message", { month: monthLabel }),
      });
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("hr.my_time.toasts.not_handed_in"),
        message: refusalMessage(failure, t, currentLocale) ?? t("hr.my_time.toasts.try_again"),
      });
    } finally {
      setIsBusy(false);
    }
  };

  if (isLoading)
    return (
      <Loader className="flex w-full flex-col gap-3">
        <Loader.Item height="96px" />
        <Loader.Item height="40px" />
        <Loader.Item height="320px" />
      </Loader>
    );

  // A failed request is not the same as having no employment record, and telling
  // somebody their hours are not being tracked when the network merely dropped
  // sends them to ask for something they already have.
  if (error)
    return (
      <div className="w-full">
        <EmptyStateCompact
          title={t("hr.shared.load_failed")}
          description={t("hr.shared.load_failed_detail")}
          assetKey="unknown"
          assetClassName="size-20"
          rootClassName="py-16"
          actions={[{ label: t("hr.shared.retry"), variant: "secondary", onClick: () => void mutate() }]}
        />
      </div>
    );

  // Somebody can be a member of the workspace without being employed through it —
  // an administrator, or a guest on one project. There is nothing to show them,
  // and saying so is better than an empty table.
  if (!data?.profile)
    return (
      <div className="w-full">
        <EmptyStateCompact
          title={t("hr.my_time.no_record")}
          description={t("hr.my_time.no_record_detail")}
          assetKey="unknown"
          assetClassName="size-20"
          rootClassName="py-16"
        />
      </div>
    );

  // A month still running cannot be handed in — the server refuses it, because a
  // submitted month stops being rebuilt and hours logged afterwards would never
  // be counted. Saying so on the button beats letting it fail on every press.
  const monthIsRunning = !!period?.to_date;
  const canHandIn = period && isPeriodEditable(period.state) && !data.has_running_timer && !monthIsRunning;

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <HrPeriodStepper
          label={monthLabel}
          onPrevious={() => setMonth(previousMonth(year, month))}
          onNext={() => setMonth(nextMonth(year, month))}
        />

        <div className="flex items-center gap-2">
          {/* One thing to do, and it is the thing somebody opened this page for.
              Everything else — the exports, the starting balance, the rebuild —
              is occasional and lives behind the menu, because six buttons of
              equal weight is a wall rather than a choice. */}
          {/* Recording time is about today, so the month comes with it. Opening
              today's form while the page still showed March asked the March
              period whether the day was editable — so a closed March made
              today's form read-only, and a closed today would have let March be
              edited. */}
          <Button
            variant="secondary"
            size="lg"
            onClick={() => {
              setMonth([now.getFullYear(), now.getMonth() + 1]);
              setOpenDay(todayIso);
            }}
            prependIcon={<Plus />}
          >
            {t("hr.my_time.record_time")}
          </Button>

          {period && period.state !== EHrPeriodState.LOCKED ? (
            <Tooltip
              tooltipContent={
                monthIsRunning
                  ? t("hr.my_time.cannot_hand_in.month_running")
                  : t("hr.my_time.cannot_hand_in.timer_running")
              }
              disabled={canHandIn ?? false}
              position="bottom"
            >
              {/* A wrapper, because a disabled button receives no pointer events
                  of its own and would leave somebody staring at a grey control
                  with no way to find out why. */}
              <span>
                <Button
                  variant="primary"
                  size="lg"
                  onClick={handleSubmit}
                  disabled={!canHandIn}
                  loading={isBusy}
                  prependIcon={<Send />}
                >
                  {t("hr.my_time.hand_in")}
                </Button>
              </span>
            </Tooltip>
          ) : null}

          <CustomMenu
            customButton={
              <span className="grid size-7 place-items-center rounded-md text-tertiary transition-colors hover:bg-layer-2 hover:text-primary">
                <MoreHorizontal className="size-4" />
              </span>
            }
            placement="bottom-end"
            closeOnSelect
          >
            <CustomMenu.MenuItem onClick={() => setShowOpening(true)} className="flex items-center gap-2">
              <Scale className="size-3 shrink-0" />
              {t("hr.my_time.opening")}
            </CustomMenu.MenuItem>
            {period ? (
              <>
                <CustomMenu.MenuItem
                  onClick={() => window.open(hrService.periodExportUrl(period.id, "csv"), "_self")}
                  className="flex items-center gap-2"
                >
                  <Download className="size-3 shrink-0" />
                  {t("hr.my_time.export_csv")}
                </CustomMenu.MenuItem>
                <CustomMenu.MenuItem
                  onClick={() => window.open(hrService.periodExportUrl(period.id, "xlsx"), "_self")}
                  className="flex items-center gap-2"
                >
                  <Download className="size-3 shrink-0" />
                  {t("hr.my_time.export_excel")}
                </CustomMenu.MenuItem>
              </>
            ) : null}
            {period && isPeriodEditable(period.state) ? (
              <CustomMenu.MenuItem onClick={handleRecompute} className="flex items-center gap-2">
                <RefreshCw className="size-3 shrink-0" />
                {t("hr.my_time.bring_up_to_date")}
              </CustomMenu.MenuItem>
            ) : null}
            {/* Everybody's own hours, not just a manager's view of somebody's.
                The month has only ever shown a figure a day, and the question it
                invites — on what — belongs to the person being asked about it
                first. */}
            <CustomMenu.MenuItem
              onClick={() => navigate(`/${workspaceSlug}/team-time/detail`)}
              className="flex items-center gap-2"
            >
              <ListTree className="size-3 shrink-0" />
              {t("hr.detail.title")}
            </CustomMenu.MenuItem>
            {data.is_hr_manager ? (
              <CustomMenu.MenuItem
                onClick={() => navigate(`/${workspaceSlug}/team-time`)}
                className="flex items-center gap-2"
              >
                <Users className="size-3 shrink-0" />
                {t("hr.my_time.everyone")}
              </CustomMenu.MenuItem>
            ) : null}
          </CustomMenu>
        </div>
      </div>

      <HrMonthSummary
        period={period}
        hasRunningTimer={data.has_running_timer}
        contractedWeeklyMinutes={data.schedule?.weekly_minutes ?? data.contract?.weekly_minutes ?? null}
        teleworkDaysThisYear={data.telework_days_this_year}
        leave={data.leave}
        schedule={data.schedule}
      />

      <HrStatementPanel periodId={period?.id ?? null} arrangement={data.contract?.arrangement ?? null} />

      <HrDayTable
        days={days}
        countedThrough={period?.to_date ? period.to_date.counted_through : undefined}
        onPickDay={setOpenDay}
      />

      {/* Keyed by the day: opening a different one is a different form, and the
          key is what empties it rather than an effect that fires after a render
          with the previous day's entry still in the boxes. */}
      <HrDayEntriesModal
        key={openDay ?? "none"}
        workDate={openDayInThisMonth}
        profileId={data.profile?.id ?? null}
        isLocked={!period || !isPeriodEditable(period.state)}
        recordsAttendance={!!data.contract?.records_attendance}
        onClose={() => setOpenDay(null)}
        onChanged={() => void mutate()}
      />

      <HrOpeningBalanceModal
        person={showOpening ? data.profile : null}
        isOwn
        canRecord={false}
        onClose={() => setShowOpening(false)}
      />
    </div>
  );
});
