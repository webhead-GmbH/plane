/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Check } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { AlertModalCore, EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// services
import {
  HrService,
  type THrEmploymentProfile,
  type THrLeaveEntitlement,
  type THrWorkSchedule,
} from "@/services/hr.service";
// local imports
import { formatDayWithYear, formatMinutes, inDays, parseDuration, refusalMessage } from "./utils";

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
  const { t, currentLocale } = useTranslation();
  const [yearStart, setYearStart] = useState("");
  const [yearEnd, setYearEnd] = useState("");
  const [entitlement, setEntitlement] = useState("");
  const [carryover, setCarryover] = useState("");
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [agreeing, setAgreeing] = useState<THrLeaveEntitlement | null>(null);

  const { data: rows, mutate } = useSWR(person ? `HR_LEAVE_${person.id}` : null, () =>
    person ? hrService.leaveEntitlements(person.id) : null
  );

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.leave.toasts.refused"),
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.leave.toasts.try_again"),
    });

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

    // Any overlap at all, not merely the same first day. A leave year laid over
    // an existing one wins wherever it starts later, so the carry-over in the
    // older row quietly stops applying and everything taken since the
    // anniversary is charged against a year nobody meant to open.
    if (years.some((row) => row.leave_year_start <= yearEnd && row.leave_year_end >= yearStart)) {
      setProblem(t("hr.leave.errors.overlapping_year"));
      return;
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

  const handleAgree = async () => {
    const row = agreeing;
    if (!person || !row) return;
    setIsBusy(true);
    try {
      await hrService.updateLeaveEntitlement(person.id, row.id, { is_final: true });
      await mutate();
      setAgreeing(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.leave.toasts.agreed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const years = rows ?? [];

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
    <ModalCore isOpen={person !== null} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXXL}>
      <div className="flex max-h-[80vh] flex-col gap-4 overflow-y-auto p-5">
        <div>
          <h3 className="text-16 font-medium text-primary">
            {t("hr.leave.title", { person: person?.member_display_name || person?.member_email || "" })}
          </h3>
          <p className="text-13 text-tertiary">{t("hr.leave.hint")}</p>
        </div>

        {years.length === 0 ? (
          <p className="text-13 text-tertiary">{t("hr.leave.none_yet")}</p>
        ) : (
          <div className="divide-y divide-subtle rounded-md border border-subtle">
            {years.map((row) => {
              const days = inDays(row.granted_minutes, schedule);
              return (
                <div key={row.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
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
                  {/* Only the row being acted on spins. One busy flag serves the
                      whole dialog, and every Agree button going into the loading
                      state at once left nobody able to see which figure they had
                      just frozen for good. */}
                  {row.is_final ? (
                    <span className="flex items-center gap-1 text-13 text-success-primary">
                      <Check className="size-3.5" />
                      {t("hr.leave.agreed")}
                    </span>
                  ) : (
                    <Button
                      variant="secondary"
                      size="lg"
                      loading={isBusy && agreeing?.id === row.id}
                      disabled={isBusy}
                      onClick={() => setAgreeing(row)}
                    >
                      {t("hr.leave.agree")}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
          <p className="text-13 font-medium text-secondary">{t("hr.leave.add")}</p>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="text-13 text-tertiary" htmlFor="hr-leave-start">
                {t("hr.leave.year_start")}
              </label>
              <input
                id="hr-leave-start"
                type="date"
                value={yearStart}
                onChange={(event) => setYearStart(event.target.value)}
                className="w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
              />
            </div>

            <div>
              <label className="text-13 text-tertiary" htmlFor="hr-leave-end">
                {t("hr.leave.year_end")}
              </label>
              <input
                id="hr-leave-end"
                type="date"
                value={yearEnd}
                onChange={(event) => setYearEnd(event.target.value)}
                className="w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
              />
            </div>

            <div>
              <label className="text-13 text-tertiary" htmlFor="hr-leave-entitlement">
                {t("hr.leave.entitlement_with_unit")}
              </label>
              <input
                id="hr-leave-entitlement"
                type="text"
                value={entitlement}
                placeholder={t("hr.leave.duration_placeholder")}
                onChange={(event) => setEntitlement(event.target.value)}
                className="w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
              />
              {entitlementEcho ? <span className="text-11 text-tertiary">{entitlementEcho}</span> : null}
            </div>

            <div>
              <label className="text-13 text-tertiary" htmlFor="hr-leave-carryover">
                {t("hr.leave.carryover")}
              </label>
              <input
                id="hr-leave-carryover"
                type="text"
                value={carryover}
                placeholder={t("hr.leave.carryover_placeholder")}
                onChange={(event) => setCarryover(event.target.value)}
                className="w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
              />
            </div>
          </div>

          <div>
            <label className="text-13 text-tertiary" htmlFor="hr-leave-note">
              {t("hr.leave.basis")}
            </label>
            <input
              id="hr-leave-note"
              type="text"
              value={note}
              placeholder={t("hr.leave.basis_placeholder")}
              onChange={(event) => setNote(event.target.value)}
              className="w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
            />
          </div>

          {problem && (
            <p role="alert" className="text-13 text-danger-primary">
              {problem}
            </p>
          )}

          <div className="flex justify-end">
            <Button variant="primary" size="lg" loading={isBusy} onClick={() => void handleAdd()}>
              {t("hr.leave.add_button")}
            </Button>
          </div>
        </div>

        <div className="flex justify-end">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("hr.leave.close")}
          </Button>
        </div>
      </div>

      <AlertModalCore
        isOpen={agreeing !== null}
        handleClose={() => setAgreeing(null)}
        handleSubmit={() => void handleAgree()}
        isSubmitting={isBusy}
        variant="primary"
        title={t("hr.leave.confirm_agree_title")}
        content={t("hr.leave.confirm_agree_body", {
          duration: agreeing ? formatMinutes(agreeing.granted_minutes) : "",
        })}
        primaryButtonText={{ default: t("hr.leave.agree"), loading: t("hr.leave.agreeing") }}
        secondaryButtonText={t("common.cancel")}
      />
    </ModalCore>
  );
};
