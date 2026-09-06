/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Link } from "react-router";
import { CalendarClock, Check, ChevronLeft, ChevronRight, Plus, Settings2, Trash2, X } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import {
  EHrAbsenceState,
  EHrGranularity,
  HrService,
  type THrAbsence,
  type THrEmploymentProfile,
} from "@/services/hr.service";
// local imports
import { HrAbsenceModal, type TAbsenceDraft } from "./absence-modal";
import { HrAbsenceTypesModal } from "./absence-types-modal";
import { formatDayLabel, formatMinutes, formatMonthLabel, nextMonth, previousMonth, refusalMessage } from "./utils";

const hrService = new HrService();

const STATE_KEY: Record<number, string> = {
  [EHrAbsenceState.DRAFT]: "draft",
  [EHrAbsenceState.REQUESTED]: "requested",
  [EHrAbsenceState.APPROVED]: "approved",
  [EHrAbsenceState.REJECTED]: "rejected",
  [EHrAbsenceState.CANCELLED]: "cancelled",
};

const STATE_TONE: Record<number, string> = {
  [EHrAbsenceState.DRAFT]: "bg-custom-background-80 text-custom-text-300",
  [EHrAbsenceState.REQUESTED]: "bg-amber-500/10 text-amber-600",
  [EHrAbsenceState.APPROVED]: "bg-green-500/10 text-green-600",
  [EHrAbsenceState.REJECTED]: "bg-red-500/10 text-red-600",
  [EHrAbsenceState.CANCELLED]: "bg-custom-background-80 text-custom-text-400 line-through",
};

/** First and last day of a month, as the window the list is asked for. */
const monthWindow = (year: number, month: number) => ({
  from: `${year}-${String(month).padStart(2, "0")}-01`,
  to: new Date(year, month, 0).toISOString().slice(0, 10),
});

/**
 * Who is away, and when.
 *
 * A month at a time, because that is the unit everything else here closes in and
 * an absence is only interesting next to the month it changes. The window catches
 * an absence that merely touches the month, so a holiday running over a month end
 * appears in both — dropping it from the second would hide days that are missing
 * from that month's target.
 */
export const HrAbsencesRoot = observer(function HrAbsencesRoot({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [personFilter, setPersonFilter] = useState("");
  const [recording, setRecording] = useState(false);
  const [editing, setEditing] = useState<THrAbsence | null>(null);
  const [managingTypes, setManagingTypes] = useState(false);
  const [isBusy, setIsBusy] = useState(false);

  const { from, to } = monthWindow(year, month);

  const {
    data: absences,
    isLoading,
    error,
    mutate,
  } = useSWR(`HR_ABSENCES_${from}_${to}_${personFilter}`, () =>
    hrService.absences(from, to, personFilter || undefined)
  );
  const { data: people } = useSWR("HR_EMPLOYEES", () => hrService.employees());
  const { data: types, mutate: refreshTypes } = useSWR("HR_ABSENCE_TYPES", () => hrService.absenceTypes());

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.absences.toasts.refused"),
      message: refusalMessage(failure) ?? t("hr.absences.toasts.try_again"),
    });

  const step = (move: (year: number, month: number) => [number, number]) => {
    const [nextYear, nextMonthNumber] = move(year, month);
    setYear(nextYear);
    setMonth(nextMonthNumber);
  };

  const handleSave = async (draft: TAbsenceDraft) => {
    setIsBusy(true);
    try {
      if (editing) await hrService.updateAbsence(editing.id, { ...draft });
      else await hrService.createAbsence({ ...draft });
      await mutate();
      setRecording(false);
      setEditing(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.absences.toasts.saved") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleDecide = async (absence: THrAbsence, decision: "approve" | "reject" | "cancel") => {
    setIsBusy(true);
    try {
      await hrService.decideAbsence(absence.id, decision);
      await mutate();
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleRemove = async (absence: THrAbsence) => {
    setIsBusy(true);
    try {
      await hrService.removeAbsence(absence.id);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.absences.toasts.removed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  if (error)
    return (
      <div className="mx-auto w-full max-w-6xl px-6 py-6">
        <div className="border-custom-border-200 bg-custom-background-90 rounded-md border px-4 py-6">
          <p className="text-custom-text-200 text-sm font-medium">{t("hr.team_time.not_permitted")}</p>
          <p className="text-custom-text-300 text-sm mt-1">{t("hr.absences.not_permitted_detail")}</p>
        </div>
      </div>
    );

  const rows = absences ?? [];
  const nameFor = (profileId: string) =>
    (people ?? []).find((person: THrEmploymentProfile) => person.id === profileId)?.member_display_name ?? "—";

  const monthLabel = formatMonthLabel(from);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-6 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-custom-text-100 text-lg font-semibold">{t("hr.absences.title")}</h1>
          <p className="text-custom-text-300 text-sm">{t("hr.absences.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Link to={`/${workspaceSlug}/team-time`}>
            <Button variant="secondary" size="sm" prependIcon={<CalendarClock className="size-4" />}>
              {t("hr.people.back_to_month")}
            </Button>
          </Link>
          <Button
            variant="secondary"
            size="sm"
            prependIcon={<Settings2 className="size-4" />}
            onClick={() => setManagingTypes(true)}
          >
            {t("hr.absences.manage_types")}
          </Button>
          <Button
            variant="primary"
            size="sm"
            prependIcon={<Plus className="size-4" />}
            onClick={() => {
              setEditing(null);
              setRecording(true);
            }}
          >
            {t("hr.absences.record")}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="border-custom-border-200 flex items-center gap-1 rounded-md border px-1 py-0.5">
          <button
            type="button"
            className="text-custom-text-300 hover:text-custom-text-100 p-1"
            aria-label={t("hr.absences.previous_month")}
            onClick={() => step(previousMonth)}
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="text-custom-text-200 text-sm min-w-[9rem] text-center font-medium">{monthLabel}</span>
          <button
            type="button"
            className="text-custom-text-300 hover:text-custom-text-100 p-1"
            aria-label={t("hr.absences.next_month")}
            onClick={() => step(nextMonth)}
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <select
          className="border-custom-border-200 bg-custom-background-100 text-custom-text-200 text-sm rounded-md border px-3 py-1.5"
          value={personFilter}
          onChange={(event) => setPersonFilter(event.target.value)}
        >
          <option value="">{t("hr.absences.everyone")}</option>
          {(people ?? []).map((person) => (
            <option key={person.id} value={person.id}>
              {person.member_display_name}
            </option>
          ))}
        </select>
      </div>

      <HrAbsenceModal
        isOpen={recording || editing !== null}
        absence={editing}
        people={people ?? []}
        types={types ?? []}
        isBusy={isBusy}
        onClose={() => {
          setRecording(false);
          setEditing(null);
        }}
        onSave={(draft) => void handleSave(draft)}
      />

      <HrAbsenceTypesModal
        isOpen={managingTypes}
        types={types ?? []}
        onClose={() => setManagingTypes(false)}
        onChanged={() => refreshTypes()}
      />

      {isLoading ? (
        <Loader className="flex flex-col gap-3">
          <Loader.Item height="48px" />
          <Loader.Item height="220px" />
        </Loader>
      ) : rows.length === 0 ? (
        <div className="border-custom-border-200 bg-custom-background-90 text-custom-text-300 text-sm rounded-md border px-4 py-8 text-center">
          {t("hr.absences.none_this_month")}
        </div>
      ) : (
        <div className="border-custom-border-200 overflow-x-auto rounded-md border">
          <table className="text-sm w-full min-w-[52rem]">
            <thead className="bg-custom-background-90 text-custom-text-400 text-xs tracking-wide uppercase">
              <tr>
                <th className="px-4 py-2 text-left font-medium">{t("hr.absences.column_person")}</th>
                <th className="px-4 py-2 text-left font-medium">{t("hr.absences.column_reason")}</th>
                <th className="px-4 py-2 text-left font-medium">{t("hr.absences.column_when")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("hr.absences.column_away")}</th>
                <th className="px-4 py-2 text-left font-medium">{t("hr.absences.column_state")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("hr.absences.column_action")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((absence) => {
                const locked = Boolean(absence.locked_period);
                const settled =
                  absence.state === EHrAbsenceState.CANCELLED || absence.state === EHrAbsenceState.REJECTED;

                return (
                  <tr key={absence.id} className="border-custom-border-200 hover:bg-custom-background-90/60 border-t">
                    <td className="text-custom-text-100 px-4 py-2">{nameFor(absence.profile)}</td>
                    <td className="text-custom-text-200 px-4 py-2">
                      {absence.absence_type_name || absence.absence_type_code}
                      {absence.reason && <span className="text-custom-text-400 text-xs ml-2">{absence.reason}</span>}
                    </td>
                    <td className="text-custom-text-200 px-4 py-2">
                      {absence.start_date === absence.end_date
                        ? formatDayLabel(absence.start_date)
                        : `${formatDayLabel(absence.start_date)} – ${formatDayLabel(absence.end_date)}`}
                      {absence.granularity !== EHrGranularity.FULL_DAY && (
                        <span className="text-custom-text-400 text-xs ml-2">
                          {absence.granularity === EHrGranularity.HALF_DAY
                            ? t("hr.absences.granularity.half_day")
                            : t("hr.absences.granularity.hours")}
                        </span>
                      )}
                    </td>
                    <td className="text-custom-text-200 px-4 py-2 text-right tabular-nums">
                      {formatMinutes(absence.total_minutes)}
                    </td>
                    <td className="px-4 py-2">
                      <span className={cn("text-xs rounded px-1.5 py-0.5 font-medium", STATE_TONE[absence.state])}>
                        {t(`hr.absences.state.${STATE_KEY[absence.state]}`)}
                      </span>
                      {locked && (
                        <span className="text-custom-text-400 text-xs ml-2">{t("hr.absences.month_locked")}</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {absence.state === EHrAbsenceState.REQUESTED && !locked && (
                          <>
                            <button
                              type="button"
                              className="text-custom-text-300 hover:text-green-600"
                              aria-label={t("hr.absences.approve")}
                              disabled={isBusy}
                              onClick={() => void handleDecide(absence, "approve")}
                            >
                              <Check className="size-4" />
                            </button>
                            <button
                              type="button"
                              className="text-custom-text-300 hover:text-red-500"
                              aria-label={t("hr.absences.reject")}
                              disabled={isBusy}
                              onClick={() => void handleDecide(absence, "reject")}
                            >
                              <X className="size-4" />
                            </button>
                          </>
                        )}
                        {!locked && !settled && (
                          <button
                            type="button"
                            className="text-custom-text-300 hover:text-custom-text-100 text-xs"
                            disabled={isBusy}
                            onClick={() => setEditing(absence)}
                          >
                            {t("common.edit")}
                          </button>
                        )}
                        {!locked && (
                          <button
                            type="button"
                            className="text-custom-text-400 hover:text-red-500"
                            aria-label={t("hr.absences.delete")}
                            disabled={isBusy}
                            onClick={() => void handleRemove(absence)}
                          >
                            <Trash2 className="size-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
});
