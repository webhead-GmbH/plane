/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import { observer } from "mobx-react";
import { Link } from "react-router";
import { AlertTriangle, CalendarClock, CheckCircle2, MinusCircle, Undo2, Upload } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import {
  EHrImportKind,
  EHrImportState,
  HrService,
  type THrImportBatch,
  type THrImportRow,
} from "@/services/hr.service";
// local imports
import { HrReasonModal } from "./reason-modal";
import { formatDayLabel, refusalMessage } from "./utils";

const hrService = new HrService();

const KINDS = [EHrImportKind.TIME_ENTRIES, EHrImportKind.ABSENCES, EHrImportKind.OPENING_BALANCES];

const KIND_KEY: Record<number, string> = {
  [EHrImportKind.TIME_ENTRIES]: "time_entries",
  [EHrImportKind.ABSENCES]: "absences",
  [EHrImportKind.OPENING_BALANCES]: "opening_balances",
};

/**
 * Bringing months in from whatever recorded them before.
 *
 * Every file is checked before anything is written, and the check is shown row
 * by row: this is the step where somebody finds out that six rows name an email
 * nobody logs in as, while the file can still be fixed rather than after its
 * hours are already in somebody's month.
 *
 * Applying is a separate press from uploading, and it is undoable as a unit,
 * because the alternative to both is unpicking one spreadsheet's rows from
 * another's by hand.
 */
export const HrImportRoot = observer(function HrImportRoot({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const fileField = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<EHrImportKind>(EHrImportKind.TIME_ENTRIES);
  const [checking, setChecking] = useState<THrImportBatch | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [undoing, setUndoing] = useState<THrImportBatch | null>(null);

  const { data: batches, isLoading, error, mutate } = useSWR("HR_IMPORTS", () => hrService.imports());

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.imports.toasts.refused"),
      message: refusalMessage(failure) ?? t("hr.imports.toasts.try_again"),
    });

  const handleFile = async (file: File) => {
    setIsBusy(true);
    try {
      const batch = await hrService.checkImport(file, kind);
      setChecking(batch);
      await mutate();
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
      if (fileField.current) fileField.current.value = "";
    }
  };

  const handleApply = async () => {
    if (!checking) return;
    setIsBusy(true);
    try {
      const applied = await hrService.applyImport(checking.id);
      setChecking(null);
      await mutate();
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("hr.imports.toasts.applied"),
        message: t("hr.imports.toasts.written", { count: applied.written }),
      });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleUndo = async (reason: string) => {
    if (!undoing) return;
    setIsBusy(true);
    try {
      const undone = await hrService.undoImport(undoing.id, reason);
      setUndoing(null);
      await mutate();
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("hr.imports.toasts.undone"),
        message: t("hr.imports.toasts.removed", { count: undone.removed }),
      });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  if (isLoading)
    return (
      <Loader className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-6 py-6">
        <Loader.Item height="48px" />
        <Loader.Item height="220px" />
      </Loader>
    );

  if (error)
    return (
      <div className="mx-auto w-full max-w-5xl px-6 py-6">
        <div className="border-custom-border-200 bg-custom-background-90 rounded-md border px-4 py-6">
          <p className="text-custom-text-200 text-sm font-medium">{t("hr.team_time.not_permitted")}</p>
          <p className="text-custom-text-300 text-sm mt-1">{t("hr.imports.not_permitted_detail")}</p>
        </div>
      </div>
    );

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-6 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-custom-text-100 text-lg font-semibold">{t("hr.imports.title")}</h1>
          <p className="text-custom-text-300 text-sm">{t("hr.imports.subtitle")}</p>
        </div>
        <Link to={`/${workspaceSlug}/team-time`}>
          <Button variant="secondary" size="sm" prependIcon={<CalendarClock className="size-4" />}>
            {t("hr.people.back_to_month")}
          </Button>
        </Link>
      </div>

      <section className="border-custom-border-200 flex flex-col gap-3 rounded-md border p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-custom-text-300 text-xs font-medium">{t("hr.imports.what_kind")}</span>
            <select
              value={kind}
              onChange={(e) => setKind(Number(e.target.value) as EHrImportKind)}
              className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 text-sm rounded-md border px-3 py-1.5 outline-none"
            >
              {KINDS.map((value) => (
                <option key={value} value={value}>
                  {t(`hr.imports.kind.${KIND_KEY[value]}`)}
                </option>
              ))}
            </select>
          </label>
          <input
            ref={fileField}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleFile(file);
            }}
          />
          <Button
            variant="primary"
            size="sm"
            loading={isBusy}
            prependIcon={<Upload className="size-4" />}
            onClick={() => fileField.current?.click()}
          >
            {t("hr.imports.choose_file")}
          </Button>
        </div>
        <p className="text-custom-text-400 text-xs">{t(`hr.imports.columns.${KIND_KEY[kind]}`)}</p>
      </section>

      {checking ? (
        <ImportPreview
          batch={checking}
          isBusy={isBusy}
          onApply={() => void handleApply()}
          onDiscard={() => setChecking(null)}
        />
      ) : null}

      <HrReasonModal
        isOpen={undoing !== null}
        title={t("hr.imports.undo_title", { filename: undoing?.filename ?? "" })}
        body={t("hr.imports.undo_body")}
        label={t("hr.imports.undo_label")}
        placeholder={t("hr.imports.undo_placeholder")}
        confirmLabel={t("hr.imports.undo_confirm")}
        cancelLabel={t("hr.imports.undo_cancel")}
        isBusy={isBusy}
        onClose={() => setUndoing(null)}
        onConfirm={(reason) => void handleUndo(reason)}
      />

      <section className="flex flex-col gap-2">
        <h2 className="text-custom-text-200 text-sm font-medium">{t("hr.imports.past")}</h2>
        {(batches ?? []).length === 0 ? (
          <p className="text-custom-text-400 text-sm">{t("hr.imports.none_yet")}</p>
        ) : (
          <div className="border-custom-border-200 divide-custom-border-100 divide-y rounded-md border">
            {(batches ?? []).map((batch) => (
              <div key={batch.id} className="flex flex-wrap items-center gap-3 px-4 py-2">
                <span className="text-custom-text-100 text-sm flex-1 truncate">{batch.filename}</span>
                <span className="text-custom-text-400 text-xs">{t(`hr.imports.kind.${KIND_KEY[batch.kind]}`)}</span>
                <span className="text-custom-text-300 text-xs tabular-nums">
                  {t("hr.imports.row_summary", { valid: batch.valid_count, total: batch.row_count })}
                </span>
                <span
                  className={cn(
                    "text-xs rounded px-2 py-0.5",
                    batch.state === EHrImportState.COMMITTED && "bg-green-500/10 text-green-600",
                    batch.state === EHrImportState.ROLLED_BACK && "bg-custom-background-80 text-custom-text-300",
                    batch.state === EHrImportState.FAILED && "bg-red-500/10 text-red-600"
                  )}
                >
                  {t(`hr.imports.state.${batch.state}`)}
                </span>
                {batch.state === EHrImportState.COMMITTED ? (
                  <Button
                    variant="link"
                    size="sm"
                    prependIcon={<Undo2 className="size-3.5" />}
                    onClick={() => setUndoing(batch)}
                  >
                    {t("hr.imports.undo")}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
});

const ImportPreview = ({
  batch,
  isBusy,
  onApply,
  onDiscard,
}: {
  batch: THrImportBatch;
  isBusy: boolean;
  onApply: () => void;
  onDiscard: () => void;
}) => {
  const { t } = useTranslation();
  // Errors first: they are the reason to look at this at all, and a file with
  // six bad rows out of four hundred should not need scrolling to find them.
  // Grouped rather than sorted, so file order survives inside each group.
  const rows = [
    ...batch.preview.filter((row) => row.verdict === "error"),
    ...batch.preview.filter((row) => row.verdict === "skip"),
    ...batch.preview.filter((row) => row.verdict === "ok"),
  ];

  return (
    <section className="border-custom-border-200 flex flex-col gap-3 rounded-md border p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-custom-text-100 text-sm font-medium">
            {t("hr.imports.preview_title", { filename: batch.filename })}
          </h2>
          <p className="text-custom-text-300 text-sm">{t("hr.imports.preview_hint")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={onDiscard}>
            {t("hr.imports.discard")}
          </Button>
          <Button variant="primary" size="sm" loading={isBusy} disabled={batch.valid_count === 0} onClick={onApply}>
            {t("hr.imports.apply", { count: batch.valid_count })}
          </Button>
        </div>
      </div>

      <div className="text-sm flex flex-wrap gap-4">
        <Count
          icon={<CheckCircle2 className="text-green-600 size-4" />}
          label={t("hr.imports.will_write")}
          value={batch.valid_count}
        />
        <Count
          icon={<AlertTriangle className="text-red-500 size-4" />}
          label={t("hr.imports.cannot_read")}
          value={batch.error_count}
        />
        <Count
          icon={<MinusCircle className="text-custom-text-400 size-4" />}
          label={t("hr.imports.skipped")}
          value={batch.skipped_count}
        />
      </div>

      <div className="border-custom-border-200 max-h-80 overflow-y-auto rounded-md border">
        <table className="text-sm w-full">
          <thead className="bg-custom-background-90 text-custom-text-400 text-xs uppercase">
            <tr>
              <th className="px-3 py-2 text-left font-medium">{t("hr.imports.column_row")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("hr.imports.column_verdict")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("hr.imports.column_detail")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.row} className="border-custom-border-100 border-t">
                <td className="text-custom-text-400 px-3 py-1.5 tabular-nums">{row.row}</td>
                <td className="px-3 py-1.5">
                  <span
                    className={cn(
                      "text-xs",
                      row.verdict === "ok" && "text-green-600",
                      row.verdict === "error" && "text-red-500",
                      row.verdict === "skip" && "text-custom-text-400"
                    )}
                  >
                    {t(`hr.imports.verdict.${row.verdict}`)}
                  </span>
                </td>
                <td className="text-custom-text-300 px-3 py-1.5">{row.message || describe(row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};

const Count = ({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) => (
  <span className="flex items-center gap-1.5">
    {icon}
    <span className="text-custom-text-100 tabular-nums">{value}</span>
    <span className="text-custom-text-300">{label}</span>
  </span>
);

/**
 * What a row that passed will actually write, so "apply 4 rows" is checkable.
 *
 * Every value in a preview row arrives as a string — the batch is stored as JSON
 * and read back to write from, so it keeps whatever survives that round trip.
 */
function describe(row: THrImportRow) {
  const day = row.data?.entry_date ?? row.data?.start_date ?? row.data?.effective_on;
  const minutes = Number(row.data?.minutes);
  const parts: string[] = [];
  if (typeof day === "string" && day) parts.push(formatDayLabel(day));
  if (Number.isFinite(minutes) && minutes !== 0) {
    const size = Math.abs(minutes);
    parts.push(`${minutes < 0 ? "-" : ""}${Math.floor(size / 60)}:${String(size % 60).padStart(2, "0")}`);
  }
  return parts.join(" · ");
}
