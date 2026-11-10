/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@makeplane/propel/components/button";
import { Dialog, DialogContent, DialogTitle } from "@makeplane/propel/components/dialog";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
// services
import {
  HrService,
  type THrEmploymentProfile,
  type THrLeaveEntitlement,
  type THrWorkSchedule,
} from "@/services/hr.service";
// local imports
import { HrLeaveYearForm } from "./leave-year-form";
import type { TLeaveYearPayload } from "./leave-year-form";
import { HrLeaveYearRow } from "./leave-year-row";
import { formatDayWithYear, formatMinutes, refusalMessage } from "./utils";

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
  const [isBusy, setIsBusy] = useState(false);
  const [agreeing, setAgreeing] = useState<THrLeaveEntitlement | null>(null);
  const [deleting, setDeleting] = useState<THrLeaveEntitlement | null>(null);

  const { data: rows, mutate } = useSWR(person ? `HR_LEAVE_${person.id}` : null, () =>
    person ? hrService.leaveEntitlements(person.id) : null
  );
  const years = rows ?? [];

  const complain = (failure: unknown) =>
    setToast({
      type: "error",
      title: t("hr.leave.toasts.refused"),
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.leave.toasts.try_again"),
    });

  /** Runs a change, says how it went, and rethrows a refusal so the form keeps what was typed. */
  const change = async (work: () => Promise<unknown>, success: string) => {
    try {
      await work();
      await mutate();
      setToast({ type: "success", title: success });
    } catch (failure) {
      complain(failure);
      throw failure;
    }
  };

  const handleAdd = (payload: TLeaveYearPayload) =>
    person
      ? change(() => hrService.createLeaveEntitlement(person.id, payload), t("hr.leave.toasts.added"))
      : Promise.resolve();

  const handleEdit = (row: THrLeaveEntitlement, payload: TLeaveYearPayload) =>
    person
      ? change(() => hrService.updateLeaveEntitlement(person.id, row.id, payload), t("hr.leave.toasts.saved"))
      : Promise.resolve();

  const handleAdjust = (row: THrLeaveEntitlement, minutes: number, reason: string) =>
    person
      ? change(
          () => hrService.adjustLeaveEntitlement(person.id, row.id, { minutes, reason }),
          t("hr.leave.toasts.adjusted")
        )
      : Promise.resolve();

  /** The confirmed actions: holding a figure as final, and deleting a year. */
  const confirmed = async (work: () => Promise<unknown>, success: string, done: () => void) => {
    setIsBusy(true);
    try {
      await change(work, success);
      done();
    } catch {
      // Already said; the confirmation stays open for another try.
    } finally {
      setIsBusy(false);
    }
  };

  const handleAgree = () => {
    const row = agreeing;
    if (!person || !row) return;
    void confirmed(
      () => hrService.updateLeaveEntitlement(person.id, row.id, { is_final: true }),
      t("hr.leave.toasts.agreed"),
      () => setAgreeing(null)
    );
  };

  const handleDelete = () => {
    const row = deleting;
    if (!person || !row) return;
    void confirmed(
      () => hrService.deleteLeaveEntitlement(person.id, row.id),
      t("hr.leave.toasts.deleted"),
      () => setDeleting(null)
    );
  };

  return (
    <Dialog
      open={person !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="lg">
        <div className="flex max-h-[80vh] flex-col gap-4 overflow-y-auto p-5">
          <div>
            <DialogTitle>
              {t("hr.leave.title", { person: person?.member_display_name || person?.member_email || "" })}
            </DialogTitle>
            <p className="text-13 text-tertiary">{t("hr.leave.hint")}</p>
          </div>

          {years.length === 0 ? (
            <p className="text-13 text-tertiary">{t("hr.leave.none_yet")}</p>
          ) : (
            <div className="divide-y divide-subtle rounded-md border border-subtle">
              {years.map((row) => (
                <HrLeaveYearRow
                  key={row.id}
                  row={row}
                  otherYears={years.filter((other) => other.id !== row.id)}
                  schedule={schedule}
                  isBusy={isBusy && (agreeing?.id === row.id || deleting?.id === row.id)}
                  onEdit={handleEdit}
                  onAdjust={handleAdjust}
                  onAgree={setAgreeing}
                  onDelete={setDeleting}
                />
              ))}
            </div>
          )}

          <HrLeaveYearForm
            idPrefix="hr-leave-new"
            title={t("hr.leave.add")}
            submitLabel={t("hr.leave.add_button")}
            otherYears={years}
            schedule={schedule}
            onSubmit={handleAdd}
          />

          <div className="flex justify-end">
            <Button variant="secondary" size="md" stretch="auto" label={t("hr.leave.close")} onClick={onClose} />
          </div>
        </div>

        <ConfirmDialog
          isOpen={agreeing !== null}
          handleClose={() => setAgreeing(null)}
          handleSubmit={handleAgree}
          isSubmitting={isBusy}
          variant="primary"
          title={t("hr.leave.confirm_agree_title")}
          content={t("hr.leave.confirm_agree_body", {
            duration: agreeing ? formatMinutes(agreeing.granted_minutes) : "",
          })}
          primaryButtonText={{ default: t("hr.leave.agree"), loading: t("hr.leave.agreeing") }}
          secondaryButtonText={t("common.cancel")}
        />

        <ConfirmDialog
          isOpen={deleting !== null}
          handleClose={() => setDeleting(null)}
          handleSubmit={handleDelete}
          isSubmitting={isBusy}
          variant="danger"
          title={t("hr.leave.confirm_delete_title")}
          content={t("hr.leave.confirm_delete_body", {
            duration: deleting ? formatMinutes(deleting.granted_minutes) : "",
            from: deleting ? formatDayWithYear(deleting.leave_year_start, currentLocale) : "",
            to: deleting ? formatDayWithYear(deleting.leave_year_end, currentLocale) : "",
          })}
          primaryButtonText={{ default: t("hr.leave.delete"), loading: t("hr.leave.deleting") }}
          secondaryButtonText={t("common.cancel")}
        />
      </DialogContent>
    </Dialog>
  );
};
