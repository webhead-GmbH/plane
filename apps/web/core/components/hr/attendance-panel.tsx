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
import { AlertModalCore } from "@plane/ui";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
// services
import { EHrWorkLocation, HrService, type THrAttendanceDay } from "@/services/hr.service";
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

/** The break field is a count of minutes, not a duration: "30" is half an hour, never thirty. */
const breakTaken = (value: string) => (value.trim() ? Number(value) : 0);

/**
 * Finishing before the time you started can only mean the work ran past
 * midnight, so it is read from the times rather than asked about separately — a
 * checkbox that is only ever right one way is a checkbox to get wrong. Finishing
 * at exactly the time you started is left alone: it is somebody typing the same
 * time twice, and reading it as a 24-hour day would record a full day nobody
 * worked.
 */
const crossesMidnight = (start: string, end: string) => !!end && end < start;

/**
 * What the times on screen would come to if they were saved.
 *
 * Typing 07:00 instead of 17:00 reads as a shift ending the next morning, and
 * the only way to notice is to be told the length it produces. Worked out the
 * way the save works it out, break and all — a warning about a different length
 * from the one that would be recorded is worse than none.
 */
const netIfSaved = (start: string, end: string, breakMinutes: string) => {
  if (!start || !end) return 0;
  const span = clockMinutes(end) - clockMinutes(start) + (crossesMidnight(start, end) ? 24 * 60 : 0);
  const taken = breakTaken(breakMinutes);
  return Math.max(span - (Number.isFinite(taken) ? taken : 0), 0);
};

/** What the fields say before anybody touches them: the stored day, or an empty one. */
const asTyped = (day: THrAttendanceDay | null) => ({
  start: toInput(day?.started_at_local ?? null),
  end: toInput(day?.ended_at_local ?? null),
  breakMinutes: day ? String(day.break_minutes) : "",
  where: day?.work_location ?? EHrWorkLocation.OFFICE,
});

/** The fields as somebody left them. */
type TDraft = ReturnType<typeof asTyped> & {
  problem: string | null;
};

/** Which day and which record the fields are answers about. */
const subjectOf = (workDate: string | null, day: THrAttendanceDay | null) => `${workDate}:${day?.id ?? "none"}`;

/** The fields as a stored day would fill them in, with nothing yet to complain about. */
const asAsked = (day: THrAttendanceDay | null): TDraft => ({ ...asTyped(day), problem: null });

/**
 * Whether the fields on screen say something the stored day does not.
 *
 * The break is compared as the number of minutes it stands for, because an empty
 * field and a stored zero are the same answer — a day saved without a break
 * would otherwise go on claiming it had not been saved.
 */
const unsavedIn = (draft: TDraft, day: THrAttendanceDay | null) => {
  const stored = asTyped(day);
  return (
    draft.start !== stored.start ||
    draft.end !== stored.end ||
    breakTaken(draft.breakMinutes) !== breakTaken(stored.breakMinutes) ||
    draft.where !== stored.where
  );
};

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
  const { data: rows, mutate } = useSWR(workDate && profileId ? `HR_ATTENDANCE_${workDate}_${profileId}` : null, () =>
    workDate && profileId ? hrService.attendanceDays(workDate, workDate, profileId) : null
  );

  const day = (rows ?? [])[0] ?? null;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
      <HrAttendanceHeading day={day} />

      {isLocked ? (
        <HrClosedDayNote day={day} />
      ) : (
        <HrAttendanceEditor
          day={day}
          workDate={workDate}
          profileId={profileId}
          refresh={mutate}
          onChanged={onChanged}
        />
      )}
    </div>
  );
};

const HrAttendanceHeading = ({ day }: { day: THrAttendanceDay | null }) => {
  const { t } = useTranslation();

  return (
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
  );
};

/** A closed day read back rather than offered: what was recorded, and no way to disagree with it. */
const HrClosedDayNote = ({ day }: { day: THrAttendanceDay | null }) => {
  const { t } = useTranslation();

  return (
    <p className="rounded-md bg-layer-1 px-3 py-2 text-13 text-tertiary">
      {day
        ? t("hr.attendance.closed_with", {
            from: toInput(day.started_at_local),
            to: toInput(day.ended_at_local) || "—",
            duration: formatMinutes(day.net_minutes),
          })
        : t("hr.attendance.closed_without")}
    </p>
  );
};

/** The day while it can still be changed: the four things recorded about it, and both ways out. */
const HrAttendanceEditor = ({
  day,
  workDate,
  profileId,
  refresh,
  onChanged,
}: {
  day: THrAttendanceDay | null;
  workDate: string | null;
  profileId: string | null;
  refresh: () => Promise<unknown>;
  onChanged: () => void;
}) => {
  const { t, currentLocale } = useTranslation();
  const [draft, setDraft] = useState<TDraft>(() => asAsked(day));
  const [isBusy, setIsBusy] = useState(false);
  const [removing, setRemoving] = useState(false);

  // Half-typed answers are about the day and the record they were typed against.
  // When either becomes a different one — a stored day arriving from a refresh,
  // a record saved, a record removed — they stop being answers to the question
  // on screen and the stored day is shown instead. Noticed here rather than
  // afterwards, so the inputs are never rebuilt underneath a cursor and a row
  // landing from a background refresh cannot take somebody out of the field they
  // are typing in.
  const subject = subjectOf(workDate, day);
  const [answering, setAnswering] = useState(subject);
  if (answering !== subject) {
    setAnswering(subject);
    setDraft(asAsked(day));
  }

  const { start, end, breakMinutes, where, problem } = draft;
  // Somebody here only to say when they were at work fills these four fields and
  // reaches for the strongest-looking button, which belongs to the hours below
  // and knows nothing about them. Closing then throws away the record the law
  // asks to be kept, so say it is still only typed while it is still on screen.
  const unsaved = unsavedIn(draft, day);
  const edit = (answer: Partial<TDraft>) => setDraft((current) => ({ ...current, ...answer }));

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.attendance.toasts.refused"),
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.attendance.toasts.try_again"),
    });

  const runsPastMidnight = crossesMidnight(start, end);

  const handleSave = async () => {
    if (!workDate || !profileId) return;
    if (!start) {
      edit({ problem: t("hr.attendance.errors.start_required") });
      return;
    }

    const taken = breakTaken(breakMinutes);
    if (!Number.isInteger(taken) || taken < 0) {
      edit({ problem: t("hr.attendance.errors.bad_break") });
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
      edit({ problem: null });
      await refresh();
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
      await refresh();
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
    <>
      <div className="grid gap-3 sm:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className="text-13 font-medium text-tertiary">{t("hr.attendance.from")}</span>
          <input type="time" value={start} onChange={(e) => edit({ start: e.target.value })} className={inputClass} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-13 font-medium text-tertiary">{t("hr.attendance.to")}</span>
          <input type="time" value={end} onChange={(e) => edit({ end: e.target.value })} className={inputClass} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-13 font-medium text-tertiary">{t("hr.attendance.break")}</span>
          <input
            type="number"
            min={0}
            max={480}
            value={breakMinutes}
            placeholder="30"
            onChange={(e) => edit({ breakMinutes: e.target.value })}
            className={inputClass}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-13 font-medium text-tertiary">{t("hr.attendance.where")}</span>
          <select
            value={where}
            onChange={(e) => edit({ where: Number(e.target.value) as EHrWorkLocation })}
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
          {t("hr.attendance.past_midnight_length", { duration: formatMinutes(netIfSaved(start, end, breakMinutes)) })}
        </p>
      ) : null}
      {problem ? <p className="text-13 text-danger-primary">{problem}</p> : null}

      <div className="flex items-center justify-end gap-2">
        {unsaved ? (
          <span className="mr-auto inline-flex items-center gap-1.5 text-13 text-warning-primary">
            <AlertTriangle className="size-3.5 shrink-0" />
            {t("hr.attendance.not_saved_yet")}
          </span>
        ) : null}
        {day ? (
          <HrRowAction
            icon={<Trash2 className="size-4" />}
            label={t("hr.attendance.remove")}
            danger
            disabled={isBusy}
            onClick={() => setRemoving(true)}
          />
        ) : null}
        <Button variant="primary" size="lg" loading={isBusy} onClick={() => void handleSave()}>
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
        secondaryButtonText={t("common.cancel")}
      />
    </>
  );
};

const inputClass =
  "border-subtle bg-layer-1 text-primary focus:border-accent-strong w-full rounded-md border px-3 py-1.5 text-13 outline-none";
