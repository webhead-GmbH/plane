/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "react-router";
import { CalendarDays, CalendarOff, Download, ListTree, MoreHorizontal, Upload, UserCog } from "lucide-react";
import useSWR from "swr";
// plane imports
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { useTranslation } from "@plane/i18n";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { AlertModalCore, CustomMenu, Loader } from "@plane/ui";
// local imports
import { EHrPeriodState, HrService, type THrOverviewRow } from "@/services/hr.service";
import { HrFigure } from "./figure";
import { HrNavLink } from "./nav-link";
import { HrPeriodStepper } from "./period-stepper";
import { HrOverviewTable } from "./overview-table";
import { HrReviewDaysModal } from "./review-days-modal";
import { HrReasonModal } from "./reason-modal";
import {
  balanceTone,
  figuresToShow,
  formatBalance,
  formatDayLabel,
  formatMinutes,
  formatMonthLabel,
  nextMonth,
  previousMonth,
  refusalMessage,
} from "./utils";

const hrService = new HrService();

/**
 * What the whole company's month comes to.
 *
 * Summed from exactly what each row displays, so the tiles are the total of the
 * table and not a second, differently-scoped answer above it.
 */
const monthTotals = (rows: THrOverviewRow[]) => {
  const shownRows = rows.map((row) => figuresToShow(row));
  return {
    owed: shownRows.reduce((total, row) => total + (row.target ?? 0), 0),
    worked: shownRows.reduce((total, row) => total + (row.actual ?? 0), 0),
    balance: shownRows.reduce((total, row) => total + (row.balance ?? 0), 0),
    partialThrough: shownRows.find((row) => row.isPartial)?.countedThrough ?? null,
    outstanding: rows.filter((row) => row.state !== EHrPeriodState.LOCKED).length,
  };
};

/**
 * The month for everybody, and the place it gets closed.
 *
 * Not tied to a workspace, because the people are the same people wherever they
 * are working — the same reason the personal view is not. A manager opens this
 * from whichever workspace they happen to be in and sees the whole company.
 */
export const HrTeamMonthRoot = observer(function HrTeamMonthRoot() {
  const now = new Date();
  const [[year, month], setMonth] = useState<[number, number]>(() =>
    previousMonth(now.getFullYear(), now.getMonth() + 1)
  );
  const [busyPeriodId, setBusyPeriodId] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<THrOverviewRow | null>(null);
  const [reopening, setReopening] = useState<THrOverviewRow | null>(null);
  const [closing, setClosing] = useState<THrOverviewRow | null>(null);

  const { t, currentLocale } = useTranslation();
  const { workspaceSlug } = useParams();
  const { data, isLoading, error, mutate } = useSWR(`HR_OVERVIEW_${year}_${month}`, () =>
    hrService.overview(year, month)
  );
  const notAllowed = (error as { status?: number } | undefined)?.status === 403;

  const rows = data?.rows ?? [];
  const monthLabel = formatMonthLabel(`${year}-${String(month).padStart(2, "0")}-01`, currentLocale);
  const { owed, worked, balance, partialThrough, outstanding } = monthTotals(rows);

  /** Whether it was done, so a caller can tell a month that moved from one that did not. */
  const act = async (row: THrOverviewRow, work: () => Promise<unknown>, done: string) => {
    setBusyPeriodId(row.id);
    try {
      await work();
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: done });
      return true;
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("hr.team_time.toasts.refused"),
        message: refusalMessage(failure, t, currentLocale) ?? t("hr.team_time.toasts.try_again"),
      });
      return false;
    } finally {
      setBusyPeriodId(null);
    }
  };

  const handleReopen = async (reason: string) => {
    const row = reopening;
    if (!row) return;
    // The dialog stays where it is when the month refuses to move: the reason is
    // required and was typed by hand, and closing over it asks for it twice.
    if (await act(row, () => hrService.reopen(row.id, reason), t("hr.team_time.toasts.reopened"))) {
      setReopening(null);
    }
  };

  return (
    <div className="flex w-full flex-col gap-7">
      <TeamMonthToolbar
        year={year}
        month={month}
        monthLabel={monthLabel}
        workspaceSlug={workspaceSlug}
        onPrevious={() => setMonth(previousMonth(year, month))}
        onNext={() => setMonth(nextMonth(year, month))}
      />

      {isLoading ? (
        <Loader className="flex flex-col gap-3">
          <Loader.Item height="72px" />
          <Loader.Item height="320px" />
        </Loader>
      ) : error && (notAllowed || !data) ? (
        <TeamMonthUnavailable notAllowed={notAllowed} onRetry={() => void mutate()} />
      ) : (
        <>
          <TeamMonthFigures
            owed={owed}
            worked={worked}
            balance={balance}
            outstanding={outstanding}
            people={rows.length}
          />

          <HrOverviewTable
            rows={rows}
            busyPeriodId={busyPeriodId}
            onApprove={(row) => void act(row, () => hrService.approve(row.id), t("hr.team_time.toasts.agreed"))}
            onLock={setClosing}
            onReopen={setReopening}
            onReview={setReviewing}
          />

          <CloseMonthDialog
            row={closing}
            busyPeriodId={busyPeriodId}
            onClose={() => setClosing(null)}
            onConfirm={() =>
              void act(closing!, () => hrService.lock(closing!.id), t("hr.team_time.toasts.closed")).then(() =>
                setClosing(null)
              )
            }
          />

          <ReviewFlaggedDaysDialog row={reviewing} onClose={() => setReviewing(null)} onSettled={() => void mutate()} />

          <ReopenMonthDialog
            row={reopening}
            monthLabel={monthLabel}
            busyPeriodId={busyPeriodId}
            onClose={() => setReopening(null)}
            onConfirm={(reason) => void handleReopen(reason)}
          />

          <TeamMonthNote partialThrough={partialThrough} />
        </>
      )}
    </div>
  );
});

type TToolbarProps = {
  year: number;
  month: number;
  /** The month being read, already written out for a person. */
  monthLabel: string;
  workspaceSlug: string | undefined;
  onPrevious: () => void;
  onNext: () => void;
};

/**
 * Which month is being read, where else in the module to go, and the exports.
 *
 * Four of these six were links to other pages, dressed as actions and weighted
 * the same as the exports. Somewhere to go is not something to do, and a row of
 * six identical buttons makes the reader sort out which is which.
 */
const TeamMonthToolbar = ({ year, month, monthLabel, workspaceSlug, onPrevious, onNext }: TToolbarProps) => {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <HrPeriodStepper label={monthLabel} onPrevious={onPrevious} onNext={onNext} />

      <div className="flex items-center gap-2">
        <nav className="flex items-center gap-1">
          <HrNavLink to={`/${workspaceSlug}/team-time/detail`} icon={<ListTree className="size-4" />}>
            {t("hr.detail.title")}
          </HrNavLink>
          <HrNavLink to={`/${workspaceSlug}/team-time/people`} icon={<UserCog className="size-4" />}>
            {t("hr.people.title")}
          </HrNavLink>
          <HrNavLink to={`/${workspaceSlug}/team-time/absences`} icon={<CalendarOff className="size-4" />}>
            {t("hr.absences.title")}
          </HrNavLink>
          <HrNavLink to={`/${workspaceSlug}/team-time/holidays`} icon={<CalendarDays className="size-4" />}>
            {t("hr.holidays.title")}
          </HrNavLink>
          <HrNavLink to={`/${workspaceSlug}/team-time/import`} icon={<Upload className="size-4" />}>
            {t("hr.imports.title")}
          </HrNavLink>
        </nav>

        <span className="mx-1 h-4 w-px bg-layer-3" aria-hidden />

        <CustomMenu
          customButton={
            <span className="grid size-7 place-items-center rounded-md text-tertiary transition-colors hover:bg-layer-2 hover:text-primary">
              <MoreHorizontal className="size-4" />
            </span>
          }
          placement="bottom-end"
          closeOnSelect
        >
          <CustomMenu.MenuItem
            onClick={() => window.open(hrService.monthExportUrl(year, month, "csv"), "_self")}
            className="flex items-center gap-2"
          >
            <Download className="size-3 shrink-0" />
            {t("hr.team_time.export_csv")}
          </CustomMenu.MenuItem>
          <CustomMenu.MenuItem
            onClick={() => window.open(hrService.monthExportUrl(year, month, "xlsx"), "_self")}
            className="flex items-center gap-2"
          >
            <Download className="size-3 shrink-0" />
            {t("hr.team_time.export_excel")}
          </CustomMenu.MenuItem>
        </CustomMenu>
      </div>
    </div>
  );
};

type TUnavailableProps = {
  /** Whether the month is being withheld rather than merely missing. */
  notAllowed: boolean;
  onRetry: () => void;
};

/**
 * Standing in for the month when it cannot be shown.
 *
 * Being refused everybody's month is not a failure and offers nothing to retry:
 * the reader is pointed at their own month instead, which is the page they are
 * entitled to.
 */
const TeamMonthUnavailable = ({ notAllowed, onRetry }: TUnavailableProps) => {
  const { t } = useTranslation();
  return (
    <EmptyStateCompact
      title={notAllowed ? t("hr.team_time.not_permitted") : t("hr.shared.load_failed")}
      description={
        notAllowed
          ? t("hr.team_time.not_permitted_detail", { page: t("hr.my_time.title") })
          : t("hr.shared.load_failed_detail")
      }
      assetKey={notAllowed ? "members" : "unknown"}
      assetClassName="size-20"
      rootClassName="py-16"
      actions={notAllowed ? undefined : [{ label: t("hr.shared.retry"), variant: "secondary", onClick: onRetry }]}
    />
  );
};

type TFiguresProps = {
  owed: number;
  worked: number;
  balance: number;
  /** Months still to be closed. */
  outstanding: number;
  /** How many people have a month at all, which is what the open count is out of. */
  people: number;
};

/** The company's month in four figures, above the table they are summed from. */
const TeamMonthFigures = ({ owed, worked, balance, outstanding, people }: TFiguresProps) => {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <HrFigure label={t("hr.summary.owed")} value={formatMinutes(owed)} />
      <HrFigure label={t("hr.summary.worked")} value={formatMinutes(worked)} />
      <HrFigure
        label={t("hr.summary.balance")}
        value={formatBalance(balance)}
        tone={balanceTone(balance)}
        accent={balance < 0 ? "border-danger-strong/40 bg-danger-subtle" : "border-subtle bg-surface-1"}
      />
      <HrFigure
        label={t("hr.team_time.still_open")}
        value={t("hr.team_time.open_count", { open: outstanding, total: people })}
      />
    </div>
  );
};

type TCloseMonthProps = {
  /** Whose month is about to be closed, or null while nobody's is. */
  row: THrOverviewRow | null;
  busyPeriodId: string | null;
  onClose: () => void;
  onConfirm: () => void;
};

/** Closing somebody's month, which is asked about by name because it is theirs. */
const CloseMonthDialog = ({ row, busyPeriodId, onClose, onConfirm }: TCloseMonthProps) => {
  const { t } = useTranslation();
  return (
    <AlertModalCore
      isOpen={row !== null}
      handleClose={onClose}
      handleSubmit={onConfirm}
      isSubmitting={busyPeriodId === row?.id}
      variant="primary"
      title={t("hr.team_time.confirm_close_title", { person: row?.member_display_name ?? "" })}
      content={t("hr.team_time.confirm_close_body")}
      primaryButtonText={{
        default: t("hr.overview_table.close"),
        loading: t("hr.team_time.closing"),
      }}
    />
  );
};

type TReviewFlaggedDaysProps = {
  /** Whose flagged days are being looked at, or null while nobody's are. */
  row: THrOverviewRow | null;
  onClose: () => void;
  onSettled: () => void;
};

/**
 * The days one person's month is refusing to close on.
 *
 * Keyed by the row, so opening a second person's flagged days is a fresh form
 * rather than the first person's notes still in the boxes.
 */
const ReviewFlaggedDaysDialog = ({ row, onClose, onSettled }: TReviewFlaggedDaysProps) => (
  <HrReviewDaysModal
    key={row?.id ?? "none"}
    periodId={row?.id ?? null}
    personName={row?.member_display_name ?? ""}
    onClose={onClose}
    onSettled={onSettled}
  />
);

type TReopenMonthProps = {
  /** Whose month is being put back, or null while nobody's is. */
  row: THrOverviewRow | null;
  monthLabel: string;
  busyPeriodId: string | null;
  onClose: () => void;
  onConfirm: (reason: string) => void;
};

/** Putting a closed month back, which nobody may do without saying why. */
const ReopenMonthDialog = ({ row, monthLabel, busyPeriodId, onClose, onConfirm }: TReopenMonthProps) => {
  const { t } = useTranslation();
  return (
    <HrReasonModal
      key={row?.id ?? "none"}
      isOpen={row !== null}
      title={t("hr.reopen.title", { month: monthLabel })}
      body={t("hr.reopen.body", { person: row?.member_display_name ?? "" })}
      label={t("hr.reopen.label")}
      placeholder={t("hr.reopen.placeholder")}
      confirmLabel={t("hr.reopen.confirm")}
      cancelLabel={t("hr.reopen.cancel")}
      isBusy={busyPeriodId === row?.id}
      onClose={onClose}
      onConfirm={onConfirm}
    />
  );
};

type TNoteProps = {
  /** How far a month still running has been counted, where one is. */
  partialThrough: string | null;
};

/** What the figures above are as of, and where the hours behind them came from. */
const TeamMonthNote = ({ partialThrough }: TNoteProps) => {
  const { t, currentLocale } = useTranslation();
  return (
    <p className="text-13 text-tertiary">
      {partialThrough
        ? `${t("hr.team_time.as_things_stand", { date: formatDayLabel(partialThrough, currentLocale) })} `
        : ""}
      {t("hr.team_time.counted_anywhere")}
    </p>
  );
};
