/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// services
import { HrService, type THrAbsenceType } from "@/services/hr.service";

const hrService = new HrService();

type TProps = {
  isOpen: boolean;
  types: THrAbsenceType[];
  onClose: () => void;
  onChanged: () => Promise<unknown>;
};

/** A blank type, set up as ordinary paid leave — much the commonest thing to add. */
const BLANK = {
  code: "",
  name_de: "",
  credits_actual: true,
  consumes_leave_entitlement: false,
  is_paid: true,
};

/**
 * The reasons for being away this company recognises.
 *
 * The two switches are the whole point of a type and decide the arithmetic, so
 * they are shown as plain questions rather than as flags. Whether the day still
 * counts as worked separates paid leave and sickness from unpaid leave; whether
 * it comes off the leave account separates annual leave from everything else.
 *
 * A type in use is never deleted — the absences filed under it would lose their
 * meaning — so it is retired instead and stops being offered for anything new.
 */
export const HrAbsenceTypesModal = ({ isOpen, types, onClose, onChanged }: TProps) => {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(BLANK);
  const [isBusy, setIsBusy] = useState(false);

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.absences.types.refused"),
      message: (failure as { error?: string })?.error ?? t("hr.absences.types.try_again"),
    });

  const handleAdd = async () => {
    if (!draft.code.trim() || !draft.name_de.trim()) return;

    setIsBusy(true);
    try {
      await hrService.createAbsenceType({
        ...draft,
        code: draft.code.trim().toUpperCase(),
        name_de: draft.name_de.trim(),
      });
      await onChanged();
      setDraft(BLANK);
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleToggleActive = async (type: THrAbsenceType) => {
    setIsBusy(true);
    try {
      await hrService.updateAbsenceType(type.id, { is_active: !type.is_active });
      await onChanged();
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleRemove = async (type: THrAbsenceType) => {
    setIsBusy(true);
    try {
      await hrService.removeAbsenceType(type.id);
      await onChanged();
    } catch (failure) {
      // The server refuses to delete a type that absences still point at, which
      // is the right answer — those records would otherwise lose their reason.
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const field =
    "border-custom-border-200 bg-custom-background-100 text-custom-text-100 w-full rounded-md border px-3 py-1.5 text-sm";

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXL}>
      <div className="flex flex-col gap-4 p-5">
        <div>
          <h3 className="text-custom-text-100 text-base font-semibold">{t("hr.absences.types.title")}</h3>
          <p className="text-custom-text-300 text-sm">{t("hr.absences.types.subtitle")}</p>
        </div>

        <div className="border-custom-border-200 overflow-x-auto rounded-md border">
          <table className="text-sm w-full min-w-[40rem]">
            <thead className="bg-custom-background-90 text-custom-text-400 text-xs tracking-wide uppercase">
              <tr>
                <th className="px-3 py-2 text-left font-medium">{t("hr.absences.types.column_code")}</th>
                <th className="px-3 py-2 text-left font-medium">{t("hr.absences.types.column_name")}</th>
                <th className="px-3 py-2 text-center font-medium">{t("hr.absences.types.column_counts")}</th>
                <th className="px-3 py-2 text-center font-medium">{t("hr.absences.types.column_leave")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("hr.absences.types.column_action")}</th>
              </tr>
            </thead>
            <tbody>
              {types.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-custom-text-300 px-3 py-6 text-center">
                    {t("hr.absences.types.none_yet")}
                  </td>
                </tr>
              )}
              {types.map((type) => (
                <tr key={type.id} className="border-custom-border-200 border-t">
                  <td className="text-custom-text-200 font-mono text-xs px-3 py-2">{type.code}</td>
                  <td className="px-3 py-2">
                    <span className={type.is_active ? "text-custom-text-100" : "text-custom-text-400 line-through"}>
                      {type.name_de || type.name_en}
                    </span>
                  </td>
                  <td className="text-custom-text-300 px-3 py-2 text-center">
                    {type.credits_actual ? t("common.yes") : t("common.no")}
                  </td>
                  <td className="text-custom-text-300 px-3 py-2 text-center">
                    {type.consumes_leave_entitlement ? t("common.yes") : t("common.no")}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        className="text-custom-text-300 hover:text-custom-text-100 text-xs"
                        disabled={isBusy}
                        onClick={() => void handleToggleActive(type)}
                      >
                        {type.is_active ? t("hr.absences.types.retire") : t("hr.absences.types.bring_back")}
                      </button>
                      <button
                        type="button"
                        className="text-custom-text-400 hover:text-red-500"
                        aria-label={t("hr.absences.types.delete")}
                        disabled={isBusy}
                        onClick={() => void handleRemove(type)}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="border-custom-border-200 flex flex-col gap-3 rounded-md border p-3">
          <p className="text-custom-text-200 text-sm font-medium">{t("hr.absences.types.add")}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              className={field}
              value={draft.code}
              placeholder={t("hr.absences.types.code_placeholder")}
              onChange={(event) => setDraft({ ...draft, code: event.target.value })}
            />
            <input
              className={field}
              value={draft.name_de}
              placeholder={t("hr.absences.types.name_placeholder")}
              onChange={(event) => setDraft({ ...draft, name_de: event.target.value })}
            />
          </div>
          <label className="text-custom-text-300 text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.credits_actual}
              onChange={(event) => setDraft({ ...draft, credits_actual: event.target.checked })}
            />
            {t("hr.absences.types.counts_as_worked")}
          </label>
          <label className="text-custom-text-300 text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.consumes_leave_entitlement}
              onChange={(event) => setDraft({ ...draft, consumes_leave_entitlement: event.target.checked })}
            />
            {t("hr.absences.types.draws_on_leave")}
          </label>
          <div className="flex justify-end">
            <Button
              variant="primary"
              size="sm"
              prependIcon={<Plus className="size-4" />}
              disabled={isBusy || !draft.code.trim() || !draft.name_de.trim()}
              onClick={() => void handleAdd()}
            >
              {t("hr.absences.types.add_button")}
            </Button>
          </div>
        </div>

        <div className="flex items-center justify-end">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("close")}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
};
