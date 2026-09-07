/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { AlertTriangle, Check } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { EModalPosition, EModalWidth, Loader, ModalCore } from "@plane/ui";
// services
import { HrService, type THrPeriodDay } from "@/services/hr.service";
// local imports
import { formatDayLabel, formatMinutes, refusalMessage } from "./utils";

const hrService = new HrService();

type TProps = {
  /** The month whose flagged days are being looked at, or null when closed. */
  periodId: string | null;
  personName: string;
  onClose: () => void;
  /** The month is unblocked once the last day is settled, so the caller refreshes. */
  onSettled: () => void;
};

/**
 * The days a month is refusing to close on, and what was decided about them.
 *
 * A day gets flagged when hours that were counted into it are no longer there.
 * The system cannot tell whether they were withdrawn deliberately or lost by
 * accident, and it will not guess: the month stays open until somebody says.
 * Until this existed the flag was a dead end — the month simply could not be
 * closed, and the screen that said so offered nothing to do about it.
 *
 * Each day is settled on its own, with its own note, because they are separate
 * questions with separate answers and one blanket sentence for a month's worth of
 * them explains nothing to the person who reads it later.
 */
export const HrReviewDaysModal = ({ periodId, personName, onClose, onSettled }: TProps) => {
  const { t, currentLocale } = useTranslation();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyDayId, setBusyDayId] = useState<string | null>(null);

  const { data, isLoading, mutate } = useSWR(periodId ? `HR_PERIOD_DAYS_${periodId}` : null, () =>
    periodId ? hrService.periodDays(periodId) : null
  );

  const flagged = (data ?? []).filter((day) => day.needs_review);

  const handleSettle = async (day: THrPeriodDay) => {
    if (!periodId) return;
    const note = (notes[day.id] ?? "").trim();
    if (!note) return;
    setBusyDayId(day.id);
    try {
      await hrService.settleDay(periodId, day.id, note);
      await mutate();
      onSettled();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.review_days.toasts.settled") });
    } catch (failure) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("hr.review_days.toasts.refused"),
        message: refusalMessage(failure, t, currentLocale) ?? t("hr.review_days.toasts.try_again"),
      });
    } finally {
      setBusyDayId(null);
    }
  };

  return (
    <ModalCore
      isOpen={periodId !== null}
      handleClose={onClose}
      position={EModalPosition.CENTER}
      width={EModalWidth.XXL}
    >
      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-start gap-3">
          <span className="flex size-9 flex-shrink-0 items-center justify-center rounded-full bg-warning-subtle">
            <AlertTriangle className="size-4 text-warning-primary" />
          </span>
          <div className="flex flex-col gap-1">
            <h3 className="text-16 font-medium text-primary">{t("hr.review_days.title", { person: personName })}</h3>
            <p className="text-13 text-tertiary">{t("hr.review_days.body")}</p>
          </div>
        </div>

        {isLoading ? (
          <Loader className="flex flex-col gap-2">
            <Loader.Item height="72px" />
            <Loader.Item height="72px" />
          </Loader>
        ) : flagged.length === 0 ? (
          <p className="rounded-md bg-layer-1 px-3 py-2 text-13 text-tertiary">{t("hr.review_days.all_settled")}</p>
        ) : (
          <div className="flex flex-col gap-3">
            {flagged.map((day) => (
              <div key={day.id} className="flex flex-col gap-2 rounded-md border border-subtle p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-13 font-medium text-primary">
                    {formatDayLabel(day.work_date, currentLocale)}
                  </span>
                  <span className="text-13 text-tertiary tabular-nums">
                    {t("hr.review_days.counts_now", { duration: formatMinutes(day.actual_minutes) })}
                  </span>
                </div>
                <label className="flex flex-col gap-1">
                  <span className="text-13 font-medium text-secondary">{t("hr.review_days.what_happened")}</span>
                  <input
                    value={notes[day.id] ?? ""}
                    onChange={(event) => setNotes((current) => ({ ...current, [day.id]: event.target.value }))}
                    placeholder={t("hr.review_days.placeholder")}
                    className="w-full rounded-md border border-subtle bg-layer-1 px-3 py-1.5 text-13 text-primary outline-none placeholder:text-tertiary focus:border-accent-strong"
                  />
                </label>
                <div className="flex justify-end">
                  <Button
                    variant="primary"
                    size="lg"
                    prependIcon={<Check />}
                    disabled={(notes[day.id] ?? "").trim().length === 0}
                    loading={busyDayId === day.id}
                    onClick={() => void handleSettle(day)}
                  >
                    {t("hr.review_days.settle")}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center justify-end">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("hr.review_days.close")}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
};
