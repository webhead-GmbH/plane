/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// services
import { EHrTimeCategory, EHrTimeSource, HrService, type THrTimeEntry } from "@/services/hr.service";
// local imports
import { formatDayLabel, formatMinutes, parseDuration } from "./utils";

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
export const HrDayEntriesModal = ({ workDate, profileId, isLocked, onClose, onChanged }: TProps) => {
  const { t } = useTranslation();
  const [minutes, setMinutes] = useState("");
  const [category, setCategory] = useState<EHrTimeCategory>(EHrTimeCategory.ADMIN);
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const { data: entries, mutate } = useSWR(
    workDate && profileId ? `HR_DAY_ENTRIES_${workDate}_${profileId}` : null,
    () => (workDate && profileId ? hrService.timeEntries(workDate, workDate, profileId) : null)
  );

  useEffect(() => {
    if (!workDate) return;
    setMinutes("");
    setCategory(EHrTimeCategory.ADMIN);
    setNote("");
    setProblem(null);
  }, [workDate]);

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
        message: (failure as { error?: string })?.error ?? t("hr.entries.toasts.try_again"),
      });
    } finally {
      setIsBusy(false);
    }
  };

  const handleDelete = async (entry: THrTimeEntry) => {
    setIsBusy(true);
    try {
      await hrService.deleteTimeEntry(entry.id);
      await mutate();
      onChanged();
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("hr.entries.toasts.refused"),
        message: (failure as { error?: string })?.error ?? t("hr.entries.toasts.try_again"),
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
        <div>
          <h3 className="text-custom-text-100 text-lg font-medium">{workDate ? formatDayLabel(workDate) : ""}</h3>
          <p className="text-custom-text-300 text-sm">{t("hr.entries.hint")}</p>
        </div>

        {mine.length > 0 ? (
          <div className="border-custom-border-200 divide-custom-border-100 divide-y rounded-md border">
            {mine.map((entry) => (
              <div key={entry.id} className="flex items-center gap-3 px-3 py-2">
                <span className="text-custom-text-100 text-sm w-16 tabular-nums">{formatMinutes(entry.minutes)}</span>
                <span className="text-custom-text-200 text-sm">
                  {t(`hr.entries.category.${CATEGORY_KEY[entry.category] ?? "admin"}`)}
                </span>
                <span className="text-custom-text-400 text-xs flex-1 truncate">{entry.note}</span>
                {entry.source === EHrTimeSource.IMPORT ? (
                  <span className="bg-custom-background-80 text-custom-text-300 text-xs rounded px-1.5 py-0.5">
                    {t("hr.entries.imported")}
                  </span>
                ) : null}
                {!isLocked && !entry.locked_period ? (
                  <button
                    type="button"
                    aria-label={t("hr.entries.remove")}
                    onClick={() => void handleDelete(entry)}
                    disabled={isBusy}
                    className="text-custom-text-400 hover:text-red-500"
                  >
                    <Trash2 className="size-4" />
                  </button>
                ) : null}
              </div>
            ))}
            <div className="text-custom-text-300 text-xs flex items-center justify-between px-3 py-2">
              <span>{t("hr.entries.day_total")}</span>
              <span className="text-custom-text-100 tabular-nums">{formatMinutes(dayTotal)}</span>
            </div>
          </div>
        ) : (
          <p className="text-custom-text-400 text-sm">{t("hr.entries.none_yet")}</p>
        )}

        {isLocked ? (
          <p className="text-custom-text-300 bg-custom-background-90 text-sm rounded-md px-3 py-2">
            {t("hr.entries.month_closed")}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="grid gap-3 sm:grid-cols-[7rem_1fr]">
              <label className="flex flex-col gap-1">
                <span className="text-custom-text-300 text-xs font-medium">{t("hr.entries.how_long")}</span>
                <input
                  value={minutes}
                  onChange={(e) => setMinutes(e.target.value)}
                  placeholder="1:30"
                  className={inputClass}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-custom-text-300 text-xs font-medium">{t("hr.entries.what_it_was")}</span>
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
              <span className="text-custom-text-300 text-xs font-medium">{t("hr.entries.note")}</span>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t("hr.entries.note_placeholder")}
                className={inputClass}
              />
            </label>
            {problem ? <p className="text-sm text-red-500">{problem}</p> : null}
          </div>
        )}

        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("hr.entries.done")}
          </Button>
          {!isLocked ? (
            <Button variant="primary" size="sm" loading={isBusy} onClick={() => void handleAdd()}>
              {t("hr.entries.add")}
            </Button>
          ) : null}
        </div>
      </div>
    </ModalCore>
  );
};

const inputClass =
  "border-custom-border-200 bg-custom-background-100 text-custom-text-100 focus:border-custom-primary-100 w-full rounded-md border px-3 py-1.5 text-sm outline-none";
