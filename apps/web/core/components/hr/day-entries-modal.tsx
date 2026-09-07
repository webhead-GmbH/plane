/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { AlertModalCore, EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// services
import { EHrTimeCategory, EHrTimeSource, HrService, type THrTimeEntry } from "@/services/hr.service";
// local imports
import { HrAttendancePanel } from "./attendance-panel";
import { formatDayLabel, formatMinutes, parseDuration, refusalMessage } from "./utils";

const hrService = new HrService();

const CATEGORIES = [
  EHrTimeCategory.MEETING,
  EHrTimeCategory.TRAINING,
  EHrTimeCategory.ADMIN,
  EHrTimeCategory.TRAVEL,
  EHrTimeCategory.ON_CALL,
  EHrTimeCategory.CORRECTION,
];

const CATEGORY_KEY: Record<number, string> = {
  [EHrTimeCategory.MEETING]: "meeting",
  [EHrTimeCategory.TRAINING]: "training",
  [EHrTimeCategory.ADMIN]: "admin",
  [EHrTimeCategory.TRAVEL]: "travel",
  [EHrTimeCategory.ON_CALL]: "on_call",
  [EHrTimeCategory.CORRECTION]: "correction",
  [EHrTimeCategory.IMPORTED]: "imported",
};

type TProps = {
  /** The day being edited, or null when the modal is closed. */
  workDate: string | null;
  profileId: string | null;
  /** A closed month is evidence; its hours cannot be moved. */
  isLocked: boolean;
  /** Whether this person's contract says their attendance is kept at all. */
  recordsAttendance?: boolean;
  onClose: () => void;
  onChanged: () => void;
};

/**
 * The hours on one day that no work item accounts for.
 *
 * This is also how a month that happened before the company used Plane gets
 * entered: pick the day, say how long and what it was. Nothing here is limited
 * to the current month, because the whole point is entering what is already
 * past — a screen that only accepted today would leave the previous system's
 * months permanently unenterable.
 */
export const HrDayEntriesModal = ({
  workDate,
  profileId,
  isLocked,
  recordsAttendance = false,
  onClose,
  onChanged,
}: TProps) => {
  const { t, currentLocale } = useTranslation();
  const [minutes, setMinutes] = useState("");
  const [category, setCategory] = useState<EHrTimeCategory>(EHrTimeCategory.ADMIN);
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  // Something typed but not yet added. Both the warning and the Add button key
  // off this, so the two can never disagree about whether there is work to lose.
  const hasUnsaved = minutes.trim() !== "" || note.trim() !== "";
  const [removing, setRemoving] = useState<THrTimeEntry | null>(null);

  const { data: entries, mutate } = useSWR(
    workDate && profileId ? `HR_DAY_ENTRIES_${workDate}_${profileId}` : null,
    () => (workDate && profileId ? hrService.timeEntries(workDate, workDate, profileId) : null)
  );

  const mine = (entries ?? []).filter((row) => row.entry_date === workDate);
  const dayTotal = mine.reduce((total, row) => total + row.minutes, 0);

  const handleAdd = async () => {
    if (!workDate || !profileId) return;
    const parsed = parseDuration(minutes);
    if (parsed === null || parsed === 0) {
      setProblem(t("hr.entries.errors.bad_duration"));
      return;
    }
    setIsBusy(true);
    try {
      await hrService.createTimeEntry({
        profile_id: profileId,
        entry_date: workDate,
        minutes: parsed,
        category,
        note: note.trim(),
      });
      setMinutes("");
      setNote("");
      setProblem(null);
      await mutate();
      onChanged();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.entries.toasts.added") });
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("hr.entries.toasts.refused"),
        message: refusalMessage(failure, t, currentLocale) ?? t("hr.entries.toasts.try_again"),
      });
    } finally {
      setIsBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!removing) return;
    setIsBusy(true);
    try {
      await hrService.deleteTimeEntry(removing.id);
      await mutate();
      setRemoving(null);
      onChanged();
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("hr.entries.toasts.refused"),
        message: refusalMessage(failure, t, currentLocale) ?? t("hr.entries.toasts.try_again"),
      });
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <ModalCore
      isOpen={workDate !== null}
      handleClose={onClose}
      position={EModalPosition.CENTER}
      width={EModalWidth.XXL}
    >
      <div className="flex flex-col gap-4 p-5">
        <h3 className="text-16 font-medium text-primary">{workDate ? formatDayLabel(workDate, currentLocale) : ""}</h3>

        {/* When they were at work comes first, and separately: it is the record the
            law asks for, and the hours below are what those hours went on. */}
        {recordsAttendance ? (
          <HrAttendancePanel workDate={workDate} profileId={profileId} isLocked={isLocked} onChanged={onChanged} />
        ) : null}

        <p className="text-13 text-tertiary">{t("hr.entries.hint")}</p>

        {mine.length > 0 ? (
          <div className="divide-y divide-subtle rounded-md border border-subtle">
            {mine.map((entry) => (
              <div key={entry.id} className="flex items-center gap-3 px-3 py-2">
                <span className="w-16 text-13 text-primary tabular-nums">{formatMinutes(entry.minutes)}</span>
                <span className="text-13 text-secondary">
                  {t(`hr.entries.category.${CATEGORY_KEY[entry.category] ?? "admin"}`)}
                </span>
                <span className="flex-1 truncate text-13 text-tertiary">{entry.note}</span>
                {entry.source === EHrTimeSource.IMPORT ? (
                  <span className="rounded bg-layer-2 px-1.5 py-0.5 text-13 text-tertiary">
                    {t("hr.entries.imported")}
                  </span>
                ) : null}
                {!isLocked && !entry.locked_period ? (
                  <button
                    type="button"
                    aria-label={t("hr.entries.remove")}
                    onClick={() => setRemoving(entry)}
                    disabled={isBusy}
                    className="text-tertiary hover:text-danger-primary"
                  >
                    <Trash2 className="size-4" />
                  </button>
                ) : null}
              </div>
            ))}
            <div className="flex items-center justify-between px-3 py-2 text-13 text-tertiary">
              <span>{t("hr.entries.day_total")}</span>
              <span className="text-primary tabular-nums">{formatMinutes(dayTotal)}</span>
            </div>
          </div>
        ) : (
          <p className="text-13 text-tertiary">{t("hr.entries.none_yet")}</p>
        )}

        {isLocked ? (
          <p className="rounded-md bg-layer-1 px-3 py-2 text-13 text-tertiary">{t("hr.entries.month_closed")}</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="grid gap-3 sm:grid-cols-[7rem_1fr]">
              <label className="flex flex-col gap-1">
                <span className="text-13 font-medium text-tertiary">{t("hr.entries.how_long")}</span>
                <input
                  value={minutes}
                  onChange={(e) => setMinutes(e.target.value)}
                  placeholder="1:30"
                  className={inputClass}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-13 font-medium text-tertiary">{t("hr.entries.what_it_was")}</span>
                <select
                  value={category}
                  onChange={(e) => setCategory(Number(e.target.value) as EHrTimeCategory)}
                  className={inputClass}
                >
                  {CATEGORIES.map((value) => (
                    <option key={value} value={value}>
                      {t(`hr.entries.category.${CATEGORY_KEY[value]}`)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="flex flex-col gap-1">
              <span className="text-13 font-medium text-tertiary">{t("hr.entries.note")}</span>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t("hr.entries.note_placeholder")}
                className={inputClass}
              />
            </label>
            {problem ? <p className="text-13 text-danger-primary">{problem}</p> : null}
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          {hasUnsaved ? (
            <span className="mr-auto inline-flex items-center gap-1.5 text-13 text-warning-primary">
              <AlertTriangle className="size-3.5" />
              {t("hr.entries.not_added_yet")}
            </span>
          ) : null}
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("hr.entries.close")}
          </Button>
          {!isLocked ? (
            <Button
              variant="primary"
              size="lg"
              loading={isBusy}
              disabled={!hasUnsaved}
              onClick={() => void handleAdd()}
            >
              {t("hr.entries.add")}
            </Button>
          ) : null}
        </div>
      </div>

      <AlertModalCore
        isOpen={removing !== null}
        handleClose={() => setRemoving(null)}
        handleSubmit={() => void handleDelete()}
        isSubmitting={isBusy}
        variant="danger"
        title={t("hr.entries.confirm_remove_title")}
        content={t("hr.entries.confirm_remove_body", {
          duration: removing ? formatMinutes(removing.minutes) : "",
        })}
        primaryButtonText={{ default: t("hr.entries.remove"), loading: t("hr.entries.removing") }}
      />
    </ModalCore>
  );
};

const inputClass =
  "border-subtle bg-layer-1 text-primary focus:border-accent-strong w-full rounded-md border px-3 py-1.5 text-13 outline-none";
