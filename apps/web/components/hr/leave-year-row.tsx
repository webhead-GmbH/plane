/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Check } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@makeplane/propel/components/button";
import { cn } from "@plane/utils";
// services
import type { THrLeaveEntitlement, THrWorkSchedule } from "@/services/hr.service";
// local imports
import { HrLeaveYearForm } from "./leave-year-form";
import type { TLeaveYearPayload } from "./leave-year-form";
import { formatBalance, formatDayWithYear, formatMinutes, inDays, parseSignedDuration } from "./utils";

type TProps = {
  row: THrLeaveEntitlement;
  otherYears: THrLeaveEntitlement[];
  schedule: THrWorkSchedule | null;
  /** True while this row is being held as final or deleted, from the dialog's confirmations. */
  isBusy: boolean;
  onEdit: (row: THrLeaveEntitlement, payload: TLeaveYearPayload) => Promise<void>;
  onAdjust: (row: THrLeaveEntitlement, minutes: number, reason: string) => Promise<void>;
  onAgree: (row: THrLeaveEntitlement) => void;
  onDelete: (row: THrLeaveEntitlement) => void;
};

/**
 * One leave year: what it grants, what has been taken and what is left.
 *
 * Until the figure is held as final it is corrected in place, or deleted. After
 * that it is adjusted: a change with its reason, listed under the year, so what
 * was agreed with the person stays readable next to what was done about it.
 */
export const HrLeaveYearRow = ({ row, otherYears, schedule, isBusy, onEdit, onAdjust, onAgree, onDelete }: TProps) => {
  const { t, currentLocale } = useTranslation();
  const [mode, setMode] = useState<"view" | "edit" | "adjust">("view");

  if (mode === "edit") {
    return (
      <div className="p-2">
        <HrLeaveYearForm
          idPrefix={`hr-leave-${row.id}`}
          title={t("hr.leave.edit_title")}
          submitLabel={t("hr.leave.save")}
          initial={row}
          otherYears={otherYears}
          schedule={schedule}
          onSubmit={async (payload) => {
            await onEdit(row, payload);
            setMode("view");
          }}
          onCancel={() => setMode("view")}
        />
      </div>
    );
  }

  const days = inDays(row.granted_minutes, schedule);
  const daysLeft = inDays(row.remaining_minutes, schedule);

  return (
    <div className="flex flex-col gap-2 px-3 py-2">
      <div className="flex flex-wrap items-center gap-3">
        <span className="w-24 text-13 text-primary tabular-nums">{formatMinutes(row.granted_minutes)}</span>
        {days ? <span className="text-13 text-tertiary">{t("hr.leave.about_days", { days })}</span> : null}
        <span className="flex-1 text-13 text-tertiary">
          {t("hr.leave.between", {
            from: formatDayWithYear(row.leave_year_start, currentLocale),
            to: formatDayWithYear(row.leave_year_end, currentLocale),
          })}
        </span>
        {row.carryover_minutes !== 0 ? (
          <span className="rounded bg-layer-2 px-1.5 py-0.5 text-13 text-tertiary">
            {t("hr.leave.carried", { duration: formatMinutes(row.carryover_minutes) })}
          </span>
        ) : null}
        {row.is_final ? (
          <span className="flex items-center gap-1 text-13 text-success-primary">
            <Check className="size-3.5" />
            {t("hr.leave.agreed")}
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span className={cn("flex-1 text-13", row.remaining_minutes < 0 ? "text-danger-primary" : "text-secondary")}>
          {t("hr.leave.taken_left", {
            taken: formatMinutes(row.taken_minutes),
            left: formatMinutes(row.remaining_minutes),
          })}
          {daysLeft ? <span className="text-tertiary"> · {t("hr.leave.left_days", { days: daysLeft })}</span> : null}
        </span>
        {row.is_final && mode === "view" ? (
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label={t("hr.leave.adjust")}
            onClick={() => setMode("adjust")}
          />
        ) : null}
        {!row.is_final ? (
          <>
            <Button
              variant="ghost"
              size="md"
              stretch="auto"
              label={t("hr.leave.edit")}
              disabled={isBusy}
              onClick={() => setMode("edit")}
            />
            <Button
              variant="ghost"
              size="md"
              stretch="auto"
              label={t("hr.leave.delete")}
              disabled={isBusy}
              onClick={() => onDelete(row)}
            />
            {/* Only the row being acted on spins: every button going into the
              loading state at once left nobody able to see which figure they had
              just frozen for good. */}
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("hr.leave.agree")}
              loading={isBusy}
              onClick={() => onAgree(row)}
            />
          </>
        ) : null}
      </div>

      {row.adjustments.length > 0 ? (
        <div className="flex flex-col gap-1 border-l-2 border-subtle pl-3">
          <p className="text-11 font-medium text-tertiary">{t("hr.leave.adjustments")}</p>
          {row.adjustments.map((adjustment) => (
            <div key={adjustment.id} className="flex flex-wrap items-baseline gap-x-2 text-13">
              <span className="w-16 text-primary tabular-nums">{formatBalance(adjustment.minutes)}</span>
              <span className="flex-1 text-secondary">{adjustment.reason}</span>
              <span className="text-11 text-tertiary">
                {t("hr.leave.adjustment_by", {
                  person: adjustment.created_by_name,
                  date: formatDayWithYear(adjustment.created_at.slice(0, 10), currentLocale),
                })}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {mode === "adjust" ? (
        <HrLeaveAdjustForm
          idPrefix={`hr-leave-adjust-${row.id}`}
          onSubmit={async (minutes, reason) => {
            await onAdjust(row, minutes, reason);
            setMode("view");
          }}
          onCancel={() => setMode("view")}
        />
      ) : null}
    </div>
  );
};

type TAdjustProps = {
  idPrefix: string;
  /** Rejects to keep the form open with what was typed; the caller says why. */
  onSubmit: (minutes: number, reason: string) => Promise<void>;
  onCancel: () => void;
};

const inputClass = "w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary";

/** A change to a figure held as final: how much, either way, and why. */
const HrLeaveAdjustForm = ({ idPrefix, onSubmit, onCancel }: TAdjustProps) => {
  const { t } = useTranslation();
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const handleSubmit = async () => {
    const minutes = parseSignedDuration(amount);
    if (minutes === null) {
      setProblem(t("hr.leave.errors.bad_duration"));
      return;
    }
    if (minutes === 0) {
      setProblem(t("hr.leave.errors.zero_change"));
      return;
    }
    if (!reason.trim()) {
      setProblem(t("hr.leave.errors.reason_required"));
      return;
    }
    setIsBusy(true);
    try {
      await onSubmit(minutes, reason.trim());
    } catch {
      // The caller has said what went wrong; what was typed stays for another try.
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
      <div>
        <p className="text-13 font-medium text-secondary">{t("hr.leave.adjust_title")}</p>
        <p className="text-13 text-tertiary">{t("hr.leave.adjust_hint")}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-[12rem_1fr]">
        <div>
          <label className="text-13 text-tertiary" htmlFor={`${idPrefix}-amount`}>
            {t("hr.leave.adjust_amount")}
          </label>
          <input
            id={`${idPrefix}-amount`}
            type="text"
            value={amount}
            placeholder={t("hr.leave.adjust_amount_placeholder")}
            onChange={(event) => setAmount(event.target.value)}
            className={inputClass}
          />
        </div>
        <div>
          <label className="text-13 text-tertiary" htmlFor={`${idPrefix}-reason`}>
            {t("hr.leave.adjust_reason")}
          </label>
          <input
            id={`${idPrefix}-reason`}
            type="text"
            value={reason}
            placeholder={t("hr.leave.adjust_reason_placeholder")}
            onChange={(event) => setReason(event.target.value)}
            className={inputClass}
          />
        </div>
      </div>
      {problem && (
        <p role="alert" className="text-13 text-danger-primary">
          {problem}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button
          variant="secondary"
          size="md"
          stretch="auto"
          label={t("common.cancel")}
          disabled={isBusy}
          onClick={onCancel}
        />
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          label={t("hr.leave.adjust_button")}
          loading={isBusy}
          onClick={() => void handleSubmit()}
        />
      </div>
    </div>
  );
};
