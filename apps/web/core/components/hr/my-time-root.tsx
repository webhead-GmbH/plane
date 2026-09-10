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
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { Button } from "@plane/propel/button";
import { useTranslation } from "@plane/i18n";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { AlertModalCore, CustomMenu, Loader } from "@plane/ui";
// local imports
import { HrService, type THrMe, type THrPeriod } from "@/services/hr.service";
import { HrDayTable } from "./day-table";
import { HrDayEntriesModal } from "./day-entries-modal";
import { HrOpeningBalanceModal } from "./opening-balance-modal";
import { HrMonthSummary } from "./month-summary";
import { HrPeriodStepper } from "./period-stepper";
import { HrStatementPanel } from "./statement-panel";
import { formatMonthLabel, isPeriodEditable, nextMonth, previousMonth, refusalMessage } from "./utils";

const hrService = new HrService();

/** Contracted hours as the schedule in force has them, and only failing that as the contract does. */
const contractedWeeklyMinutes = (me: THrMe) => me.schedule?.weekly_minutes ?? me.contract?.weekly_minutes ?? null;

type TTranslate = (key: string, values?: Record<string, unknown>) => string;

/**
 * Why the server refused, said in the reader's language where it named a reason.
 * Often it names none, and then asking again is the only honest advice.
 */
const refusalOrRetry = (failure: unknown, t: TTranslate, locale: string) =>
  refusalMessage(failure, t, locale) ?? t("hr.my_time.toasts.try_again");

/**
 * Only a day this month's period can answer for. Whether a day may be edited is
 * the period's answer, and the period on hand is the one being viewed — so a day
 * from any other month would be judged by the wrong month's state.
 */
const dayWithinMonth = (day: string | null, viewedMonth: string) => (day && day.startsWith(viewedMonth) ? day : null);

export const MyTimeRoot = observer(function MyTimeRoot() {
  const now = new Date();
  // Recording time is about today, so the button opens today rather than asking.
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const [[year, month], setMonth] = useState<[number, number]>([now.getFullYear(), now.getMonth() + 1]);
  const [isBusy, setIsBusy] = useState(false);
  const [openDay, setOpenDay] = useState<string | null>(null);
  const [showOpening, setShowOpening] = useState(false);

  const { t, currentLocale } = useTranslation();
  const { data, isLoading, error, mutate } = useSWR(`HR_ME_${year}_${month}`, () => hrService.me(year, month));

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
  // sends them to ask for something they already have. Only when there is nothing
  // else to show, though: the month refetches itself whenever the window comes
  // back into focus, and a laptop waking must not replace a month somebody is
  // reading — nor take the day form open over it, and whatever is typed in it.
  if (error && !data)
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

  const viewedMonth = `${year}-${String(month).padStart(2, "0")}`;
  const monthLabel = formatMonthLabel(`${viewedMonth}-01`, currentLocale);

  // Recording time is about today, so the month comes with it. Opening today's
  // form while the page still showed March asked the March period whether the
  // day was editable — so a closed March made today's form read-only, and a
  // closed today would have let March be edited.
  const openToday = () => {
    setMonth([now.getFullYear(), now.getMonth() + 1]);
    setOpenDay(todayIso);
  };

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <HrPeriodStepper
          label={monthLabel}
          onPrevious={() => setMonth(previousMonth(year, month))}
          onNext={() => setMonth(nextMonth(year, month))}
        />

        <MonthActions
          me={data}
          monthLabel={monthLabel}
          isBusy={isBusy}
          onBusyChange={setIsBusy}
          onRecordToday={openToday}
          onOpeningBalance={() => setShowOpening(true)}
          onRefresh={mutate}
        />
      </div>

      <MonthFigures me={data} onPickDay={setOpenDay} />

      <MonthDialogs
        me={data}
        openDay={openDay}
        viewedMonth={viewedMonth}
        showOpening={showOpening}
        onCloseDay={() => setOpenDay(null)}
        onCloseOpening={() => setShowOpening(false)}
        onChanged={() => void mutate()}
      />
    </div>
  );
});

/** Everything somebody can do about the month they are looking at. */
const MonthActions = ({
  me,
  monthLabel,
  isBusy,
  onBusyChange,
  onRecordToday,
  onOpeningBalance,
  onRefresh,
}: {
  me: THrMe;
  monthLabel: string;
  isBusy: boolean;
  onBusyChange: (value: boolean) => void;
  onRecordToday: () => void;
  onOpeningBalance: () => void;
  onRefresh: () => Promise<unknown>;
}) => {
  const { t, currentLocale } = useTranslation();
  const period = me.period;
  const [confirming, setConfirming] = useState(false);

  const handleRecompute = async () => {
    if (!period) return;
    onBusyChange(true);
    try {
      await hrService.recompute(period.id);
      await onRefresh();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.my_time.toasts.recomputed") });
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("hr.my_time.toasts.not_recomputed"),
        message: refusalOrRetry(failure, t, currentLocale),
      });
    } finally {
      onBusyChange(false);
    }
  };

  const handleSubmit = async () => {
    if (!period) return;
    onBusyChange(true);
    try {
      await hrService.submit(period.id);
      await onRefresh();
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("hr.my_time.toasts.handed_in"),
        message: t("hr.my_time.toasts.handed_in_message", { month: monthLabel }),
      });
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("hr.my_time.toasts.not_handed_in"),
        message: refusalOrRetry(failure, t, currentLocale),
      });
    } finally {
      onBusyChange(false);
      setConfirming(false);
    }
  };

  return (
    <>
      <div className="flex items-center gap-2">
        {/* One thing to do, and it is the thing somebody opened this page for.
            Everything else — the exports, the starting balance, the rebuild —
            is occasional and lives behind the menu, because six buttons of
            equal weight is a wall rather than a choice. */}
        <Button variant="secondary" size="lg" onClick={onRecordToday} prependIcon={<Plus />}>
          {t("hr.my_time.record_time")}
        </Button>

        <HandInButton
          period={period}
          hasRunningTimer={me.has_running_timer}
          isBusy={isBusy}
          onHandIn={() => setConfirming(true)}
        />

        <MonthMenu
          period={period}
          isHrManager={me.is_hr_manager}
          onOpeningBalance={onOpeningBalance}
          onRecompute={handleRecompute}
        />
      </div>

      {/* The one press on this screen that cannot be taken back by the person
          making it: the month stops being theirs to change, and only whoever
          looks after the team can give it back. Worth asking first. */}
      <AlertModalCore
        variant="primary"
        isOpen={confirming}
        handleClose={() => setConfirming(false)}
        handleSubmit={() => void handleSubmit()}
        isSubmitting={isBusy}
        title={t("hr.my_time.hand_in")}
        content={t("hr.my_time.confirm_hand_in", { month: monthLabel })}
        primaryButtonText={{ default: t("hr.my_time.hand_in"), loading: t("hr.my_time.hand_in") }}
        secondaryButtonText={t("common.cancel")}
      />
    </>
  );
};

/**
 * The one press that ends a month. Only a month that can still be changed has
 * anything left to hand in, so once it has gone the button goes with it: a grey
 * one left standing after the month was handed in says nothing the state badge
 * beside the figures does not already say, and the only reason it could give for
 * being disabled would be a timer that stopped long ago.
 */
const HandInButton = ({
  period,
  hasRunningTimer,
  isBusy,
  onHandIn,
}: {
  period: THrPeriod | null;
  hasRunningTimer: boolean;
  isBusy: boolean;
  onHandIn: () => void;
}) => {
  const { t } = useTranslation();

  if (!period || !isPeriodEditable(period.state)) return null;

  // A month still running cannot be handed in — the server refuses it, because a
  // submitted month stops being rebuilt and hours logged afterwards would never
  // be counted. Saying so on the button beats letting it fail on every press.
  const monthIsRunning = !!period.to_date;
  const canHandIn = !hasRunningTimer && !monthIsRunning;

  return (
    <Tooltip
      label={
        monthIsRunning ? t("hr.my_time.cannot_hand_in.month_running") : t("hr.my_time.cannot_hand_in.timer_running")
      }
      disabled={canHandIn}
      side="bottom"
    >
      {/* A wrapper, because a disabled button receives no pointer events
          of its own and would leave somebody staring at a grey control
          with no way to find out why. */}
      <span>
        <Button
          variant="primary"
          size="lg"
          onClick={onHandIn}
          disabled={!canHandIn}
          loading={isBusy}
          prependIcon={<Send />}
        >
          {t("hr.my_time.hand_in")}
        </Button>
      </span>
    </Tooltip>
  );
};

/** The occasional things: the starting balance, the exports, a rebuild, and the ways out of one's own month. */
const MonthMenu = ({
  period,
  isHrManager,
  onOpeningBalance,
  onRecompute,
}: {
  period: THrPeriod | null;
  isHrManager: boolean;
  onOpeningBalance: () => void;
  onRecompute: () => void;
}) => {
  const { t } = useTranslation();
  // Only used to navigate, never to decide what the figures are: the month comes
  // from the server against the signed-in person, not from the address bar.
  const { workspaceSlug } = useParams();
  const navigate = useNavigate();

  return (
    <CustomMenu
      customButton={
        <span className="grid size-7 place-items-center rounded-md text-tertiary transition-colors hover:bg-layer-2 hover:text-primary">
          <MoreHorizontal className="size-4" />
        </span>
      }
      placement="bottom-end"
      closeOnSelect
    >
      <CustomMenu.MenuItem onClick={onOpeningBalance} className="flex items-center gap-2">
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
        <CustomMenu.MenuItem onClick={onRecompute} className="flex items-center gap-2">
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
      {isHrManager ? (
        <CustomMenu.MenuItem
          onClick={() => navigate(`/${workspaceSlug}/team-time`)}
          className="flex items-center gap-2"
        >
          <Users className="size-3 shrink-0" />
          {t("hr.my_time.everyone")}
        </CustomMenu.MenuItem>
      ) : null}
    </CustomMenu>
  );
};

/** What the month came to, what it is worth to whoever invoices it, and the day-by-day behind both. */
const MonthFigures = ({ me, onPickDay }: { me: THrMe; onPickDay: (workDate: string) => void }) => {
  const period = me.period;

  return (
    <>
      <HrMonthSummary
        period={period}
        hasRunningTimer={me.has_running_timer}
        contractedWeeklyMinutes={contractedWeeklyMinutes(me)}
        teleworkDaysThisYear={me.telework_days_this_year}
        leave={me.leave}
        schedule={me.schedule}
      />

      <HrStatementPanel periodId={period?.id ?? null} arrangement={me.contract?.arrangement ?? null} />

      <HrDayTable
        days={period?.days ?? []}
        countedThrough={period?.to_date ? period.to_date.counted_through : undefined}
        onPickDay={onPickDay}
      />
    </>
  );
};

const MonthDialogs = ({
  me,
  openDay,
  viewedMonth,
  showOpening,
  onCloseDay,
  onCloseOpening,
  onChanged,
}: {
  me: THrMe;
  openDay: string | null;
  viewedMonth: string;
  showOpening: boolean;
  onCloseDay: () => void;
  onCloseOpening: () => void;
  onChanged: () => void;
}) => {
  const period = me.period;

  return (
    <>
      {/* Keyed by the day: opening a different one is a different form, and the
          key is what empties it rather than an effect that fires after a render
          with the previous day's entry still in the boxes. */}
      <HrDayEntriesModal
        key={openDay ?? "none"}
        workDate={dayWithinMonth(openDay, viewedMonth)}
        profileId={me.profile?.id ?? null}
        isLocked={!period || !isPeriodEditable(period.state)}
        recordsAttendance={!!me.contract?.records_attendance}
        onClose={onCloseDay}
        onChanged={onChanged}
      />

      {/* Keyed on the opening rather than reset by an effect: the profile comes
          from the fetched month, so it is a new object on every revalidation and
          an effect watching it emptied the form under whoever was using it. */}
      <HrOpeningBalanceModal
        key={showOpening ? (me.profile?.id ?? "own") : "closed"}
        person={showOpening ? me.profile : null}
        isOwn
        canRecord={false}
        onClose={onCloseOpening}
      />
    </>
  );
};
