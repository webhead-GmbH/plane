/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Link, useParams } from "react-router";
import { ChevronLeft, ChevronRight, Download, Upload, UserCog } from "lucide-react";
import useSWR from "swr";
// plane imports
import { Button } from "@plane/propel/button";
import { useTranslation } from "@plane/i18n";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
// local imports
import { EHrPeriodState, HrService, type THrOverviewRow } from "@/services/hr.service";
import { HrOverviewTable } from "./overview-table";
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
} from "./utils";

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
  const [reopening, setReopening] = useState<THrOverviewRow | null>(null);

  const { t, currentLocale } = useTranslation();
  const { workspaceSlug } = useParams();
  const { data, isLoading, error, mutate } = useSWR(`HR_OVERVIEW_${year}_${month}`, () =>
    hrService.overview(year, month)
  );

  const rows = data?.rows ?? [];
  const monthLabel = formatMonthLabel(`${year}-${String(month).padStart(2, "0")}-01`, currentLocale);

  // Summed from exactly what each row displays, so the tiles are the total of
  // the table and not a second, differently-scoped answer above it.
  const shownRows = rows.map((row) => figuresToShow(row));
  const owed = shownRows.reduce((total, row) => total + (row.target ?? 0), 0);
  const worked = shownRows.reduce((total, row) => total + (row.actual ?? 0), 0);
  const balance = shownRows.reduce((total, row) => total + (row.balance ?? 0), 0);
  const partialThrough = shownRows.find((row) => row.isPartial)?.countedThrough ?? null;
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
        title: t("hr.team_time.toasts.refused"),
        message: (failure as { error?: string })?.error ?? t("hr.team_time.toasts.try_again"),
      });
    } finally {
      setBusyPeriodId(null);
    }
  };

  const handleReopen = async (reason: string) => {
    const row = reopening;
    if (!row) return;
    await act(row, () => hrService.reopen(row.id, reason), t("hr.team_time.toasts.reopened"));
    setReopening(null);
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
            {t("hr.team_time.earlier")}
          </Button>
          <h1 className="text-custom-text-100 text-lg min-w-44 text-center font-semibold">{monthLabel}</h1>
          <Button
            variant="secondary"
            size="sm"
            appendIcon={<ChevronRight className="size-4" />}
            onClick={() => setMonth(nextMonth(year, month))}
          >
            {t("hr.team_time.later")}
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Link to={`/${workspaceSlug}/team-time/import`}>
            <Button variant="secondary" size="sm" prependIcon={<Upload className="size-4" />}>
              {t("hr.imports.title")}
            </Button>
          </Link>
          <Link to={`/${workspaceSlug}/team-time/people`}>
            <Button variant="secondary" size="sm" prependIcon={<UserCog className="size-4" />}>
              {t("hr.people.title")}
            </Button>
          </Link>
          <a href={hrService.monthExportUrl(year, month, "csv")} download>
            <Button variant="secondary" size="sm" prependIcon={<Download className="size-4" />}>
              {t("hr.team_time.export_csv")}
            </Button>
          </a>
          <a href={hrService.monthExportUrl(year, month, "xlsx")} download>
            <Button variant="secondary" size="sm" prependIcon={<Download className="size-4" />}>
              {t("hr.team_time.export_excel")}
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
          <p className="text-custom-text-200 text-sm font-medium">{t("hr.team_time.not_permitted")}</p>
          <p className="text-custom-text-300 text-sm mt-1">
            {t("hr.team_time.not_permitted_detail", { page: t("hr.my_time.title") })}
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="border-custom-border-200 bg-custom-background-100 flex flex-col gap-0.5 rounded-md border px-4 py-3">
              <span className="text-custom-text-400 text-xs font-medium tracking-wide uppercase">
                {t("hr.summary.owed")}
              </span>
              <span className="text-custom-text-100 text-2xl font-semibold tabular-nums">{formatMinutes(owed)}</span>
            </div>
            <div className="border-custom-border-200 bg-custom-background-100 flex flex-col gap-0.5 rounded-md border px-4 py-3">
              <span className="text-custom-text-400 text-xs font-medium tracking-wide uppercase">
                {t("hr.summary.worked")}
              </span>
              <span className="text-custom-text-100 text-2xl font-semibold tabular-nums">{formatMinutes(worked)}</span>
            </div>
            <div className="border-custom-border-200 bg-custom-background-100 flex flex-col gap-0.5 rounded-md border px-4 py-3">
              <span className="text-custom-text-400 text-xs font-medium tracking-wide uppercase">
                {t("hr.summary.balance")}
              </span>
              <span className={`text-2xl font-semibold tabular-nums ${balanceTone(balance)}`}>
                {formatBalance(balance)}
              </span>
            </div>
            <div className="border-custom-border-200 bg-custom-background-100 flex flex-col gap-0.5 rounded-md border px-4 py-3">
              <span className="text-custom-text-400 text-xs font-medium tracking-wide uppercase">
                {t("hr.team_time.still_open")}
              </span>
              <span className="text-custom-text-100 text-2xl font-semibold tabular-nums">
                {t("hr.team_time.open_count", { open: outstanding, total: rows.length })}
              </span>
            </div>
          </div>

          <HrOverviewTable
            rows={rows}
            busyPeriodId={busyPeriodId}
            onApprove={(row) => void act(row, () => hrService.approve(row.id), t("hr.team_time.toasts.agreed"))}
            onLock={(row) => void act(row, () => hrService.lock(row.id), t("hr.team_time.toasts.closed"))}
            onReopen={setReopening}
          />

          <HrReasonModal
            isOpen={reopening !== null}
            title={t("hr.reopen.title", { month: monthLabel })}
            body={t("hr.reopen.body", { person: reopening?.member_display_name ?? "" })}
            label={t("hr.reopen.label")}
            placeholder={t("hr.reopen.placeholder")}
            confirmLabel={t("hr.reopen.confirm")}
            cancelLabel={t("hr.reopen.cancel")}
            isBusy={busyPeriodId === reopening?.id}
            onClose={() => setReopening(null)}
            onConfirm={(reason) => void handleReopen(reason)}
          />

          <p className="text-custom-text-400 text-xs">
            {partialThrough
              ? `${t("hr.team_time.as_things_stand", { date: formatDayLabel(partialThrough, currentLocale) })} `
              : ""}
            {t("hr.team_time.counted_anywhere")}
          </p>
        </>
      )}
    </div>
  );
});
