/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { AlertModalCore } from "@plane/ui";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
// services
import { EHrWorkLocation, HrService } from "@/services/hr.service";
// local imports
import { formatMinutes, refusalMessage } from "./utils";

import { HrRowAction } from "./row-action";

/** "09:30" as minutes since midnight. */
const clockMinutes = (value: string) => {
  const [hours, minutes] = value.split(":").map(Number);
  return (hours || 0) * 60 + (minutes || 0);
};

const hrService = new HrService();

const WHERE = [EHrWorkLocation.OFFICE, EHrWorkLocation.HOME, EHrWorkLocation.ELSEWHERE];

const WHERE_KEY: Record<number, string> = {
  [EHrWorkLocation.OFFICE]: "office",
  [EHrWorkLocation.HOME]: "home",
  [EHrWorkLocation.ELSEWHERE]: "elsewhere",
};

/** "HH:MM:SS" as the server holds it, or "" — an `<input type="time">` wants "HH:MM". */
const toInput = (time: string | null) => (time ? time.slice(0, 5) : "");

type TProps = {
  workDate: string | null;
  profileId: string | null;
  /** A closed month is evidence; the day it was built from cannot move. */
  isLocked: boolean;
  onChanged: () => void;
};

/**
 * When somebody was at work on this day.
 *
 * A different record from the hours they booked to work items, and deliberately
 * so: this answers "when was this person at work", which is what the law asks
 * about, while a worklog answers what those hours went on. They are kept side by
 * side and reconciled, never merged — a day can be honestly recorded here with
 * nothing booked against it, and the discrepancy is the point.
 *
 * One row per day. Leaving and coming back is a longer break rather than a
 * second row, which is the right shape at this size and stays readable a year
 * later.
 *
 * Shown only for people whose contract says attendance is kept. It is off by
 * default and turning it on is a deliberate act, so rendering the fields for
 * everybody would invite exactly the record the switch exists to withhold.
 */
export const HrAttendancePanel = ({ workDate, profileId, isLocked, onChanged }: TProps) => {
  const { t, currentLocale } = useTranslation();
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [breakMinutes, setBreakMinutes] = useState("");
  const [where, setWhere] = useState<EHrWorkLocation>(EHrWorkLocation.OFFICE);
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [removing, setRemoving] = useState(false);

  const { data: rows, mutate } = useSWR(workDate && profileId ? `HR_ATTENDANCE_${workDate}_${profileId}` : null, () =>
    workDate && profileId ? hrService.attendanceDays(workDate, workDate, profileId) : null
  );

  const day = (rows ?? [])[0] ?? null;

  // Seeded from the stored row, and re-seeded only when a different row arrives.
  // Depending on the row object itself would reset the fields on every
  // revalidation, throwing away whatever was half-typed at the time — which is
  // exactly what the exhaustive-deps rule asks for here, so it is turned off on
  // the line below rather than satisfied.
  useEffect(() => {
    setStart(toInput(day?.started_at_local ?? null));
    setEnd(toInput(day?.ended_at_local ?? null));
    setBreakMinutes(day ? String(day.break_minutes) : "");
    setWhere(day?.work_location ?? EHrWorkLocation.OFFICE);
    setProblem(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day?.id, workDate]);

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.attendance.toasts.refused"),
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.attendance.toasts.try_again"),
    });

  // Finishing before the time you started can only mean the work ran past
  // midnight, so it is read from the times rather than asked about separately —
  // a checkbox that is only ever right one way is a checkbox to get wrong.
  // Finishing at exactly the time you started is left alone: it is somebody
  // typing the same time twice, and reading it as a 24-hour day would record a
  // full day nobody worked.
  const runsPastMidnight = !!end && end < start;

  // What this would come to if saved. Typing 07:00 instead of 17:00 reads as a
  // shift ending the next morning, and the only way to notice is to be told the
  // length it produces.
  const netIfSaved = (() => {
    if (!start || !end) return 0;
    const span = clockMinutes(end) - clockMinutes(start) + (runsPastMidnight ? 24 * 60 : 0);
    // Read exactly as handleSave reads it: this field is a count of minutes, not
    // a duration, and parsing "30" as a duration makes it thirty hours.
    const taken = breakMinutes.trim() ? Number(breakMinutes) : 0;
    return Math.max(span - (Number.isFinite(taken) ? taken : 0), 0);
  })();

  const handleSave = async () => {
    if (!workDate || !profileId) return;
    if (!start) {
      setProblem(t("hr.attendance.errors.start_required"));
      return;
    }

    const taken = breakMinutes.trim() ? Number(breakMinutes) : 0;
    if (!Number.isInteger(taken) || taken < 0) {
      setProblem(t("hr.attendance.errors.bad_break"));
      return;
    }

    const payload = {
      started_at_local: start,
      // An empty end is a day still running, not a day ending at midnight.
      ended_at_local: end || null,
      break_minutes: taken,
      crosses_midnight: runsPastMidnight,
      work_location: where,
    };

    setIsBusy(true);
    try {
      if (day) await hrService.updateAttendanceDay(day.id, payload);
      else await hrService.createAttendanceDay({ ...payload, profile_id: profileId, work_date: workDate });
      setProblem(null);
      await mutate();
      onChanged();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.attendance.toasts.saved") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleRemove = async () => {
    if (!day) return;
    setIsBusy(true);
    try {
      await hrService.deleteAttendanceDay(day.id);
      await mutate();
      setRemoving(false);
      onChanged();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.attendance.toasts.removed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-13 font-medium text-secondary">{t("hr.attendance.title")}</p>
          <p className="text-13 text-tertiary">{t("hr.attendance.hint")}</p>
        </div>
        {day ? (
          <span className="text-13 text-primary tabular-nums">
            {day.ended_at_local ? formatMinutes(day.net_minutes) : t("hr.attendance.still_running")}
          </span>
        ) : null}
      </div>

      {isLocked ? (
        <p className="rounded-md bg-layer-1 px-3 py-2 text-13 text-tertiary">
          {day
            ? t("hr.attendance.closed_with", {
                from: toInput(day.started_at_local),
                to: toInput(day.ended_at_local) || "—",
                duration: formatMinutes(day.net_minutes),
              })
            : t("hr.attendance.closed_without")}
        </p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <label className="flex flex-col gap-1">
              <span className="text-13 font-medium text-tertiary">{t("hr.attendance.from")}</span>
              <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={inputClass} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-13 font-medium text-tertiary">{t("hr.attendance.to")}</span>
              <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className={inputClass} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-13 font-medium text-tertiary">{t("hr.attendance.break")}</span>
              <input
                type="number"
                min={0}
                max={480}
                value={breakMinutes}
                placeholder="30"
                onChange={(e) => setBreakMinutes(e.target.value)}
                className={inputClass}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-13 font-medium text-tertiary">{t("hr.attendance.where")}</span>
              <select
                value={where}
                onChange={(e) => setWhere(Number(e.target.value) as EHrWorkLocation)}
                className={inputClass}
              >
                {WHERE.map((value) => (
                  <option key={value} value={value}>
                    {t(`hr.attendance.location.${WHERE_KEY[value]}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {runsPastMidnight ? (
            <p className="inline-flex items-center gap-1.5 text-13 text-warning-primary">
              <AlertTriangle className="size-3.5 shrink-0" />
              {t("hr.attendance.past_midnight_length", { duration: formatMinutes(netIfSaved) })}
            </p>
          ) : null}
          {problem ? <p className="text-13 text-danger-primary">{problem}</p> : null}

          <div className="flex items-center justify-end gap-2">
            {day ? (
              <HrRowAction
                icon={<Trash2 className="size-4" />}
                label={t("hr.attendance.remove")}
                danger
                disabled={isBusy}
                onClick={() => setRemoving(true)}
              />
            ) : null}
            <Button variant="secondary" size="lg" loading={isBusy} onClick={() => void handleSave()}>
              {day ? t("hr.attendance.update") : t("hr.attendance.record")}
            </Button>
          </div>
          <AlertModalCore
            isOpen={removing}
            handleClose={() => setRemoving(false)}
            handleSubmit={() => void handleRemove()}
            isSubmitting={isBusy}
            variant="danger"
            title={t("hr.attendance.confirm_remove_title")}
            content={t("hr.attendance.confirm_remove_body")}
            primaryButtonText={{
              default: t("hr.attendance.remove"),
              loading: t("hr.attendance.removing"),
            }}
          />
        </>
      )}
    </div>
  );
};

const inputClass =
  "border-subtle bg-layer-1 text-primary focus:border-accent-strong w-full rounded-md border px-3 py-1.5 text-13 outline-none";
