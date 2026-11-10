/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@makeplane/propel/components/button";
// services
import type { THrLeaveEntitlement, THrWorkSchedule } from "@/services/hr.service";
// local imports
import { formatMinutes, inDays, parseDuration, parseSignedDuration } from "./utils";

export type TLeaveYearPayload = Pick<
  THrLeaveEntitlement,
  "leave_year_start" | "leave_year_end" | "entitlement_minutes" | "carryover_minutes" | "basis_note"
>;

type TProps = {
  /** Distinguishes the add form's fields from an edit form's on the same dialog. */
  idPrefix: string;
  title: string;
  submitLabel: string;
  /** The year being edited; absent when adding one. */
  initial?: THrLeaveEntitlement;
  /** The person's other leave years, which this one may not overlap. */
  otherYears: THrLeaveEntitlement[];
  schedule: THrWorkSchedule | null;
  /** Rejects to keep the form open with what was typed; the caller says why. */
  onSubmit: (payload: TLeaveYearPayload) => Promise<void>;
  onCancel?: () => void;
};

const inputClass = "w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary";

/** The figures of one leave year, for adding a year or correcting one not yet held as final. */
export const HrLeaveYearForm = ({
  idPrefix,
  title,
  submitLabel,
  initial,
  otherYears,
  schedule,
  onSubmit,
  onCancel,
}: TProps) => {
  const { t } = useTranslation();
  const [yearStart, setYearStart] = useState(initial?.leave_year_start ?? "");
  const [yearEnd, setYearEnd] = useState(initial?.leave_year_end ?? "");
  const [entitlement, setEntitlement] = useState(initial ? formatMinutes(initial.entitlement_minutes) : "");
  const [carryover, setCarryover] = useState(
    initial && initial.carryover_minutes !== 0 ? formatMinutes(initial.carryover_minutes) : ""
  );
  const [note, setNote] = useState(initial?.basis_note ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const handleSubmit = async () => {
    if (!yearStart || !yearEnd) {
      setProblem(t("hr.leave.errors.dates_required"));
      return;
    }
    if (yearEnd <= yearStart) {
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
    const carried = carryover.trim() ? parseSignedDuration(carryover) : 0;
    if (carried === null) {
      setProblem(t("hr.leave.errors.bad_duration"));
      return;
    }

    // Any overlap at all, not merely the same first day. A leave year laid over
    // an existing one wins wherever it starts later, so the carry-over in the
    // older row quietly stops applying and everything taken since the
    // anniversary is charged against a year nobody meant to open.
    if (otherYears.some((row) => row.leave_year_start <= yearEnd && row.leave_year_end >= yearStart)) {
      setProblem(t("hr.leave.errors.overlapping_year"));
      return;
    }

    setIsBusy(true);
    try {
      await onSubmit({
        leave_year_start: yearStart,
        leave_year_end: yearEnd,
        entitlement_minutes: granted,
        carryover_minutes: carried,
        basis_note: note.trim(),
      });
      setProblem(null);
      if (!initial) {
        setEntitlement("");
        setCarryover("");
        setNote("");
      }
    } catch {
      // The caller has said what went wrong; what was typed stays for another try.
    } finally {
      setIsBusy(false);
    }
  };

  // What was typed, read back in days. A figure entered in the wrong unit is
  // otherwise invisible until somebody runs out of leave in March.
  const typed = parseDuration(entitlement);
  const typedInDays = typed !== null ? inDays(typed, schedule) : null;
  const entitlementEcho =
    typed !== null
      ? typedInDays !== null
        ? t("hr.leave.echo_days", { duration: formatMinutes(typed), days: typedInDays })
        : t("hr.leave.echo_hours", { duration: formatMinutes(typed) })
      : null;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
      <p className="text-13 font-medium text-secondary">{title}</p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="text-13 text-tertiary" htmlFor={`${idPrefix}-start`}>
            {t("hr.leave.year_start")}
          </label>
          <input
            id={`${idPrefix}-start`}
            type="date"
            value={yearStart}
            onChange={(event) => setYearStart(event.target.value)}
            className={inputClass}
          />
        </div>

        <div>
          <label className="text-13 text-tertiary" htmlFor={`${idPrefix}-end`}>
            {t("hr.leave.year_end")}
          </label>
          <input
            id={`${idPrefix}-end`}
            type="date"
            value={yearEnd}
            onChange={(event) => setYearEnd(event.target.value)}
            className={inputClass}
          />
        </div>

        <div>
          <label className="text-13 text-tertiary" htmlFor={`${idPrefix}-entitlement`}>
            {t("hr.leave.entitlement_with_unit")}
          </label>
          <input
            id={`${idPrefix}-entitlement`}
            type="text"
            value={entitlement}
            placeholder={t("hr.leave.duration_placeholder")}
            onChange={(event) => setEntitlement(event.target.value)}
            className={inputClass}
          />
          {entitlementEcho ? <span className="text-11 text-tertiary">{entitlementEcho}</span> : null}
        </div>

        <div>
          <label className="text-13 text-tertiary" htmlFor={`${idPrefix}-carryover`}>
            {t("hr.leave.carryover")}
          </label>
          <input
            id={`${idPrefix}-carryover`}
            type="text"
            value={carryover}
            placeholder={t("hr.leave.carryover_placeholder")}
            onChange={(event) => setCarryover(event.target.value)}
            className={inputClass}
          />
        </div>
      </div>

      <div>
        <label className="text-13 text-tertiary" htmlFor={`${idPrefix}-note`}>
          {t("hr.leave.basis")}
        </label>
        <input
          id={`${idPrefix}-note`}
          type="text"
          value={note}
          placeholder={t("hr.leave.basis_placeholder")}
          onChange={(event) => setNote(event.target.value)}
          className={inputClass}
        />
      </div>

      {problem && (
        <p role="alert" className="text-13 text-danger-primary">
          {problem}
        </p>
      )}

      <div className="flex justify-end gap-2">
        {onCancel ? (
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label={t("common.cancel")}
            disabled={isBusy}
            onClick={onCancel}
          />
        ) : null}
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          label={submitLabel}
          loading={isBusy}
          onClick={() => void handleSubmit()}
        />
      </div>
    </div>
  );
};
