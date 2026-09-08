/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import { observer } from "mobx-react";
import { AlertTriangle, CheckCircle2, Download, MinusCircle, Undo2, Upload } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
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
import { formatDayWithYear, refusalMessage } from "./utils";

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
export const HrImportRoot = observer(function HrImportRoot() {
  const { t, currentLocale } = useTranslation();
  const fileField = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<EHrImportKind>(EHrImportKind.TIME_ENTRIES);
  const [checking, setChecking] = useState<THrImportBatch | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [undoing, setUndoing] = useState<THrImportBatch | null>(null);

  const { data: batches, isLoading, error, mutate } = useSWR("HR_IMPORTS", () => hrService.imports());

  const complain = (failure: unknown) => complainAbout(failure, t, currentLocale);

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

  /** Reopen a checked file, fetching the rows the list leaves out. */
  const handleResume = async (batch: THrImportBatch) => {
    setIsBusy(true);
    try {
      setChecking(await hrService.importBatch(batch.id));
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
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
      <Loader className="flex w-full flex-col gap-7">
        <Loader.Item height="48px" />
        <Loader.Item height="220px" />
      </Loader>
    );

  const refusal = loadFailure(error, batches);
  if (refusal) return <ImportsUnavailable reason={refusal} onRetry={() => void mutate()} />;

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-13 text-tertiary">{t("hr.imports.subtitle")}</p>
      </div>

      <ImportToolbar
        kind={kind}
        fileField={fileField}
        isBusy={isBusy}
        onKindChange={setKind}
        onFile={(file) => void handleFile(file)}
      />

      {checking ? (
        <ImportPreview
          batch={checking}
          isBusy={isBusy}
          onApply={() => void handleApply()}
          onDiscard={() => setChecking(null)}
        />
      ) : null}

      <UndoImportDialog
        batch={undoing}
        isBusy={isBusy}
        onClose={() => setUndoing(null)}
        onConfirm={(reason) => void handleUndo(reason)}
      />

      <ImportHistory batches={batches} onResume={(batch) => void handleResume(batch)} onUndo={setUndoing} />
    </div>
  );
});

/** Which sort of file is being brought in, and the two ways of starting one. */
const ImportToolbar = ({
  kind,
  fileField,
  isBusy,
  onKindChange,
  onFile,
}: {
  kind: EHrImportKind;
  fileField: React.RefObject<HTMLInputElement>;
  isBusy: boolean;
  onKindChange: (kind: EHrImportKind) => void;
  onFile: (file: File) => void;
}) => {
  const { t } = useTranslation();

  return (
    <section className="flex flex-col gap-3 rounded-md border border-subtle p-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-13 font-medium text-tertiary">{t("hr.imports.what_kind")}</span>
          <select
            value={kind}
            onChange={(e) => onKindChange(Number(e.target.value) as EHrImportKind)}
            className="rounded-md border border-subtle bg-layer-1 px-3 py-1.5 text-13 text-primary outline-none"
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
            if (file) onFile(file);
          }}
        />
        <Button variant="secondary" size="lg" prependIcon={<Download />} onClick={() => downloadTemplate(kind)}>
          {t("hr.imports.template")}
        </Button>
        <Button
          variant="primary"
          size="lg"
          loading={isBusy}
          prependIcon={<Upload />}
          onClick={() => fileField.current?.click()}
        >
          {t("hr.imports.choose_file")}
        </Button>
      </div>
      <p className="text-13 text-tertiary">{t(`hr.imports.columns.${KIND_KEY[kind]}`)}</p>
    </section>
  );
};

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
  const { t, currentLocale } = useTranslation();
  // Errors first: they are the reason to look at this at all, and a file with
  // six bad rows out of four hundred should not need scrolling to find them.
  // Grouped rather than sorted, so file order survives inside each group.
  const rows = [
    ...batch.preview.filter((row) => row.verdict === "error"),
    ...batch.preview.filter((row) => row.verdict === "skip"),
    ...batch.preview.filter((row) => row.verdict === "ok"),
  ];

  return (
    <section className="flex flex-col gap-3 rounded-md border border-subtle p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-13 font-medium text-primary">
            {t("hr.imports.preview_title", { filename: batch.filename })}
          </h2>
          <p className="text-13 text-tertiary">{t("hr.imports.preview_hint")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="lg" onClick={onDiscard}>
            {t("hr.imports.discard")}
          </Button>
          <Button variant="primary" size="lg" loading={isBusy} disabled={batch.valid_count === 0} onClick={onApply}>
            {t("hr.imports.apply", { count: batch.valid_count })}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-4 text-13">
        <Count
          icon={<CheckCircle2 className="size-4 text-success-primary" />}
          label={t("hr.imports.will_write")}
          value={batch.valid_count}
        />
        <Count
          icon={<AlertTriangle className="size-4 text-danger-primary" />}
          label={t("hr.imports.cannot_read")}
          value={batch.error_count}
        />
        <Count
          icon={<MinusCircle className="size-4 text-tertiary" />}
          label={t("hr.imports.skipped")}
          value={batch.skipped_count}
        />
      </div>

      <div className="max-h-80 overflow-y-auto rounded-md border border-subtle">
        <table className="w-full text-13">
          <thead className="border-b border-subtle text-13 text-placeholder">
            <tr>
              <th className="px-3 py-2 text-left font-medium">{t("hr.imports.column_row")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("hr.imports.column_verdict")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("hr.imports.column_detail")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.row} className="border-t border-subtle">
                <td className="px-3 py-1.5 text-tertiary tabular-nums">{row.row}</td>
                <td className="px-3 py-1.5">
                  <span
                    className={cn(
                      "text-13",
                      row.verdict === "ok" && "text-success-primary",
                      row.verdict === "error" && "text-danger-primary",
                      row.verdict === "skip" && "text-tertiary"
                    )}
                  >
                    {t(`hr.imports.verdict.${row.verdict}`)}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-tertiary">{explain(row, t) || describe(row, currentLocale)}</td>
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
    <span className="text-primary tabular-nums">{value}</span>
    <span className="text-tertiary">{label}</span>
  </span>
);

/** What has been brought in before, and what became of each file. */
const ImportHistory = ({
  batches,
  onResume,
  onUndo,
}: {
  batches: THrImportBatch[] | undefined;
  onResume: (batch: THrImportBatch) => void;
  onUndo: (batch: THrImportBatch) => void;
}) => {
  const { t } = useTranslation();
  const rows = batches ?? [];

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-13 font-medium text-secondary">{t("hr.imports.past")}</h2>
      {rows.length === 0 ? (
        <p className="text-13 text-tertiary">{t("hr.imports.none_yet")}</p>
      ) : (
        <div className="divide-y divide-subtle rounded-md border border-subtle">
          {rows.map((batch) => (
            <ImportHistoryRow key={batch.id} batch={batch} onResume={onResume} onUndo={onUndo} />
          ))}
        </div>
      )}
    </section>
  );
};

const ImportHistoryRow = ({
  batch,
  onResume,
  onUndo,
}: {
  batch: THrImportBatch;
  onResume: (batch: THrImportBatch) => void;
  onUndo: (batch: THrImportBatch) => void;
}) => {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-2">
      <span className="flex-1 truncate text-13 text-primary">{batch.filename}</span>
      <span className="text-13 text-tertiary">{t(`hr.imports.kind.${KIND_KEY[batch.kind]}`)}</span>
      <span className="text-13 text-tertiary tabular-nums">
        {t("hr.imports.row_summary", { valid: batch.valid_count, total: batch.row_count })}
      </span>
      <span
        className={cn(
          "rounded px-2 py-0.5 text-13",
          batch.state === EHrImportState.COMMITTED && "bg-success-subtle text-success-primary",
          batch.state === EHrImportState.ROLLED_BACK && "bg-layer-2 text-tertiary",
          batch.state === EHrImportState.FAILED && "bg-danger-subtle text-danger-primary"
        )}
      >
        {t(`hr.imports.state.${batch.state}`)}
      </span>
      {batch.state === EHrImportState.PREVIEW_READY ? (
        <Button variant="secondary" size="lg" onClick={() => onResume(batch)}>
          {t("hr.imports.resume")}
        </Button>
      ) : null}
      {batch.state === EHrImportState.COMMITTED ? (
        <Button variant="link" size="lg" prependIcon={<Undo2 className="size-3.5" />} onClick={() => onUndo(batch)}>
          {t("hr.imports.undo")}
        </Button>
      ) : null}
    </div>
  );
};

/**
 * Taking a file's rows back out, which nobody does without saying why.
 *
 * Keyed on the batch, so each file is asked about in a dialog of its own and a
 * reason typed for one is never still sitting there for the next.
 */
const UndoImportDialog = ({
  batch,
  isBusy,
  onClose,
  onConfirm,
}: {
  batch: THrImportBatch | null;
  isBusy: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) => {
  const { t } = useTranslation();

  return (
    <HrReasonModal
      key={batch?.id ?? "none"}
      isOpen={batch !== null}
      title={t("hr.imports.undo_title", { filename: batch?.filename ?? "" })}
      body={t("hr.imports.undo_body")}
      label={t("hr.imports.undo_label")}
      placeholder={t("hr.imports.undo_placeholder")}
      confirmLabel={t("hr.imports.undo_confirm")}
      cancelLabel={t("hr.imports.undo_cancel")}
      isBusy={isBusy}
      onClose={onClose}
      onConfirm={onConfirm}
    />
  );
};

const ImportsUnavailable = ({ reason, onRetry }: { reason: TLoadFailure; onRetry: () => void }) => {
  const { t } = useTranslation();
  const notAllowed = reason === "not_permitted";

  return (
    <div className="w-full">
      <EmptyStateCompact
        title={notAllowed ? t("hr.team_time.not_permitted") : t("hr.shared.load_failed")}
        description={notAllowed ? t("hr.imports.not_permitted_detail") : t("hr.shared.load_failed_detail")}
        assetKey={notAllowed ? "members" : "unknown"}
        assetClassName="size-20"
        rootClassName="py-16"
        actions={notAllowed ? undefined : [{ label: t("hr.shared.retry"), variant: "secondary", onClick: onRetry }]}
      />
    </div>
  );
};

type TLoadFailure = "not_permitted" | "failed";

/**
 * Whether the screen has nothing left to show but the reason it is empty.
 *
 * Being told no reads differently from a load that broke, and a revalidation
 * that failed while the screen already holds good data must not replace it with
 * an error.
 */
function loadFailure(error: unknown, batches: THrImportBatch[] | undefined): TLoadFailure | null {
  if (!error) return null;
  if ((error as { status?: number } | undefined)?.status === 403) return "not_permitted";
  return batches ? null : "failed";
}

/** A spreadsheet with the right headings and one row showing the shape of each. */
function downloadTemplate(kind: EHrImportKind) {
  const sheets: Record<number, string[][]> = {
    [EHrImportKind.TIME_ENTRIES]: [
      ["email", "date", "hours", "note"],
      ["anna.berger@example.com", "2026-03-02", "7:42", "Monatsabschluss"],
    ],
    [EHrImportKind.OPENING_BALANCES]: [
      ["email", "date", "hours", "kind", "basis", "confidence"],
      ["anna.berger@example.com", "2026-01-01", "12:30", "time", "Agreed on 12 Jan", "documented"],
    ],
    [EHrImportKind.ABSENCES]: [
      ["email", "start_date", "end_date", "type"],
      ["anna.berger@example.com", "2026-03-02", "2026-03-06", "urlaub"],
    ],
  };
  const rows = sheets[kind] ?? sheets[EHrImportKind.TIME_ENTRIES];
  // Quoted throughout: a note or a basis may hold the separator, and a file
  // that breaks on somebody's comma is worse than no template at all.
  const csv = rows.map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(",")).join("\r\n");
  // A byte-order mark, because Excel reads a UTF-8 file without one as the
  // local codepage and turns every umlaut in a name into mojibake.
  const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${KIND_KEY[kind]}-template.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

/** The screen's one way of saying that the server would not do it. */
function complainAbout(failure: unknown, t: (key: string, values?: Record<string, unknown>) => string, locale: string) {
  setToast({
    type: TOAST_TYPE.ERROR,
    title: t("hr.imports.toasts.refused"),
    message: refusalMessage(failure, t, locale) ?? t("hr.imports.toasts.try_again"),
  });
}

/**
 * Why a row was refused or skipped, in the reader's language.
 *
 * The server sends a name for the reason and the values it mentions, plus the
 * English sentence it would otherwise have shown. The sentence is the fallback
 * for a batch previewed before the names existed, and for anything a future
 * version of the server refuses for a reason this one has no wording for — which
 * is better than a blank cell where the explanation should be.
 */
function explain(row: THrImportRow, t: (key: string, values?: Record<string, unknown>) => string): string {
  if (!row.reason) return row.message ?? "";
  const wording = t(`hr.imports.reasons.${row.reason}`, { ...row.detail });
  // i18next hands back the key itself when it knows nothing about it.
  return wording.startsWith("hr.imports.reasons.") ? (row.message ?? "") : wording;
}

/**
 * What a row that passed will actually write, so "apply 4 rows" is checkable.
 *
 * Every value in a preview row arrives as a string — the batch is stored as JSON
 * and read back to write from, so it keeps whatever survives that round trip.
 */
function describe(row: THrImportRow, locale?: string) {
  const day = row.data?.entry_date ?? row.data?.start_date ?? row.data?.effective_on;
  const minutes = Number(row.data?.minutes);
  const parts: string[] = [];
  // With the year: an import is nearly always of months that are not the one
  // being looked at, so "2 Mar" leaves the reader guessing which March they are
  // about to write into.
  if (typeof day === "string" && day) parts.push(formatDayWithYear(day, locale));
  if (Number.isFinite(minutes) && minutes !== 0) {
    const size = Math.abs(minutes);
    parts.push(`${minutes < 0 ? "-" : ""}${Math.floor(size / 60)}:${String(size % 60).padStart(2, "0")}`);
  }
  return parts.join(" · ");
}
