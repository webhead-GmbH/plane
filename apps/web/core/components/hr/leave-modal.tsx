/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// services
import {
  HrService,
  type THrEmploymentProfile,
  type THrLeaveEntitlement,
  type THrWorkSchedule,
} from "@/services/hr.service";
// local imports
import { formatDayWithYear, formatMinutes, parseDuration } from "./utils";

const hrService = new HrService();

type TProps = {
  person: THrEmploymentProfile | null;
  /** The person's schedule, for turning minutes into days. Null where they have none. */
  schedule: THrWorkSchedule | null;
  onClose: () => void;
};

/**
 * How much leave somebody has for a leave year.
 *
 * Held in minutes, not days. A day is not a fixed quantity for anyone working
 * uneven hours, and the moment contracted hours change mid-year a figure in days
 * stops meaning one thing — so days are worked out for display and never stored.
 * They are shown here only where the schedule says what a day is worth, because a
 * day count guessed from nothing would be worse than none.
 *
 * The leave year runs from the anniversary of joining rather than from January,
 * which is the statutory default here.
 *
 * Once a figure has been agreed with the person it stops being editable: a change
 * after that is an adjustment with its own reason, so what was agreed stays
 * readable next to what was done about it. The server refuses the edit either
 * way; saying so here means nobody has to discover that by being refused.
 */
export const HrLeaveModal = ({ person, schedule, onClose }: TProps) => {
  const { t } = useTranslation();
  const [yearStart, setYearStart] = useState("");
  const [yearEnd, setYearEnd] = useState("");
  const [entitlement, setEntitlement] = useState("");
  const [carryover, setCarryover] = useState("");
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const { data: rows, mutate } = useSWR(person ? `HR_LEAVE_${person.id}` : null, () =>
    person ? hrService.leaveEntitlements(person.id) : null
  );

  useEffect(() => {
    if (!person) return;
    setYearStart("");
    setYearEnd("");
    setEntitlement("");
    setCarryover("");
    setNote("");
    setProblem(null);
  }, [person]);

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.leave.toasts.refused"),
      message: (failure as { error?: string })?.error ?? t("hr.leave.toasts.try_again"),
    });

  /**
   * What one day of leave is worth, in minutes.
   *
   * Under a flexitime agreement it is the notional day that agreement names,
   * because the daily distribution is the person's to choose and there is no
   * "what they would have worked" to read off the schedule. Otherwise it is the
   * average of the days they are actually scheduled to work — a five-day week of
   * uneven days still has a meaningful day, and dividing by seven or by five
   * regardless would not give it.
   */
  const dailyMinutes = () => {
    if (!schedule) return null;
    if (schedule.is_flexible && schedule.notional_daily_minutes) return schedule.notional_daily_minutes;

    const worked = [
      schedule.monday_minutes,
      schedule.tuesday_minutes,
      schedule.wednesday_minutes,
      schedule.thursday_minutes,
      schedule.friday_minutes,
      schedule.saturday_minutes,
      schedule.sunday_minutes,
    ].filter((minutes) => minutes > 0);

    if (worked.length === 0) return null;
    return worked.reduce((total, minutes) => total + minutes, 0) / worked.length;
  };

  /** The same figure in days, where the schedule says what a day is worth. */
  const inDays = (minutes: number) => {
    const daily = dailyMinutes();
    if (!daily) return null;
    return (minutes / daily).toFixed(1);
  };

  const handleAdd = async () => {
    if (!person) return;
    if (!yearStart || !yearEnd) {
      setProblem(t("hr.leave.errors.dates_required"));
      return;
    }
    if (yearEnd < yearStart) {
      setProblem(t("hr.leave.errors.backwards"));
      return;
    }

    const granted = parseDuration(entitlement);
    if (granted === null) {
      setProblem(t("hr.leave.errors.bad_duration"));
      return;
    }

    // Carried-over leave can be negative: somebody may have taken next year's in
    // advance, and refusing the minus sign would make that unrecordable.
    let carried = 0;
    if (carryover.trim()) {
      const negative = carryover.trim().startsWith("-");
      const size = parseDuration(carryover.replace("-", ""));
      if (size === null) {
        setProblem(t("hr.leave.errors.bad_duration"));
        return;
      }
      carried = negative ? -size : size;
    }

    setIsBusy(true);
    try {
      await hrService.createLeaveEntitlement(person.id, {
        leave_year_start: yearStart,
        leave_year_end: yearEnd,
        entitlement_minutes: granted,
        carryover_minutes: carried,
        basis_note: note.trim(),
      });
      setEntitlement("");
      setCarryover("");
      setNote("");
      setProblem(null);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.leave.toasts.added") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleAgree = async (row: THrLeaveEntitlement) => {
    if (!person) return;
    setIsBusy(true);
    try {
      await hrService.updateLeaveEntitlement(person.id, row.id, { is_final: true });
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.leave.toasts.agreed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const years = rows ?? [];

  return (
    <ModalCore isOpen={person !== null} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXXL}>
      <div className="flex max-h-[80vh] flex-col gap-4 overflow-y-auto p-5">
        <div>
          <h3 className="text-custom-text-100 text-lg font-medium">
            {t("hr.leave.title", { person: person?.member_display_name || person?.member_email || "" })}
          </h3>
          <p className="text-custom-text-300 text-sm">{t("hr.leave.hint")}</p>
        </div>

        {years.length === 0 ? (
          <p className="text-custom-text-400 text-sm">{t("hr.leave.none_yet")}</p>
        ) : (
          <div className="border-custom-border-200 divide-custom-border-100 divide-y rounded-md border">
            {years.map((row) => {
              const days = inDays(row.granted_minutes);
              return (
                <div key={row.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
                  <span className="text-custom-text-100 text-sm w-24 tabular-nums">
                    {formatMinutes(row.granted_minutes)}
                  </span>
                  {days ? (
                    <span className="text-custom-text-300 text-xs">{t("hr.leave.about_days", { days })}</span>
                  ) : null}
                  <span className="text-custom-text-400 text-xs flex-1">
                    {t("hr.leave.between", {
                      from: formatDayWithYear(row.leave_year_start),
                      to: formatDayWithYear(row.leave_year_end),
                    })}
                  </span>
                  {row.carryover_minutes !== 0 ? (
                    <span className="bg-custom-background-80 text-custom-text-300 text-xs rounded px-1.5 py-0.5">
                      {t("hr.leave.carried", { duration: formatMinutes(row.carryover_minutes) })}
                    </span>
                  ) : null}
                  {row.is_final ? (
                    <span className="text-xs text-green-600 flex items-center gap-1">
                      <Check className="size-3.5" />
                      {t("hr.leave.agreed")}
                    </span>
                  ) : (
                    <Button variant="link" size="sm" loading={isBusy} onClick={() => void handleAgree(row)}>
                      {t("hr.leave.agree")}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="border-custom-border-200 flex flex-col gap-3 rounded-md border p-3">
          <p className="text-custom-text-200 text-sm font-medium">{t("hr.leave.add")}</p>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="text-custom-text-300 text-xs" htmlFor="hr-leave-start">
                {t("hr.leave.year_start")}
              </label>
              <input
                id="hr-leave-start"
                type="date"
                value={yearStart}
                onChange={(event) => setYearStart(event.target.value)}
                className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 text-sm w-full rounded border px-2 py-1"
              />
            </div>

            <div>
              <label className="text-custom-text-300 text-xs" htmlFor="hr-leave-end">
                {t("hr.leave.year_end")}
              </label>
              <input
                id="hr-leave-end"
                type="date"
                value={yearEnd}
                onChange={(event) => setYearEnd(event.target.value)}
                className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 text-sm w-full rounded border px-2 py-1"
              />
            </div>

            <div>
              <label className="text-custom-text-300 text-xs" htmlFor="hr-leave-entitlement">
                {t("hr.leave.entitlement")}
              </label>
              <input
                id="hr-leave-entitlement"
                type="text"
                value={entitlement}
                placeholder={t("hr.leave.duration_placeholder")}
                onChange={(event) => setEntitlement(event.target.value)}
                className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 text-sm w-full rounded border px-2 py-1"
              />
            </div>

            <div>
              <label className="text-custom-text-300 text-xs" htmlFor="hr-leave-carryover">
                {t("hr.leave.carryover")}
              </label>
              <input
                id="hr-leave-carryover"
                type="text"
                value={carryover}
                placeholder={t("hr.leave.carryover_placeholder")}
                onChange={(event) => setCarryover(event.target.value)}
                className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 text-sm w-full rounded border px-2 py-1"
              />
            </div>
          </div>

          <div>
            <label className="text-custom-text-300 text-xs" htmlFor="hr-leave-note">
              {t("hr.leave.basis")}
            </label>
            <input
              id="hr-leave-note"
              type="text"
              value={note}
              placeholder={t("hr.leave.basis_placeholder")}
              onChange={(event) => setNote(event.target.value)}
              className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 text-sm w-full rounded border px-2 py-1"
            />
          </div>

          {problem && <p className="text-xs text-red-500">{problem}</p>}

          <div className="flex justify-end">
            <Button variant="primary" size="sm" loading={isBusy} onClick={() => void handleAdd()}>
              {t("hr.leave.add_button")}
            </Button>
          </div>
        </div>

        <div className="flex justify-end">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("hr.leave.close")}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
};
