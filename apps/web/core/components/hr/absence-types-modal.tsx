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
import { AlertModalCore, EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// services
import { HrService, type THrAbsenceType } from "@/services/hr.service";

import { localName, refusalMessage } from "./utils";

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
  const { t, currentLocale } = useTranslation();
  const [draft, setDraft] = useState(BLANK);
  const [isBusy, setIsBusy] = useState(false);
  // Removing a kind of absence is asked about first, like every other deletion
  // here. The server refuses it outright once anything has been recorded as
  // that kind, so the ones that do go through are exactly the ones nobody would
  // notice were gone until they went looking for them.
  const [removing, setRemoving] = useState<THrAbsenceType | null>(null);

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.absences.types.refused"),
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.absences.types.try_again"),
    });

  const handleAdd = async () => {
    if (!draft.code.trim() || !draft.name_de.trim()) return;

    setIsBusy(true);
    try {
      await hrService.createAbsenceType({
        ...draft,
        code: draft.code.trim().toUpperCase(),
        name_de: draft.name_de.trim(),
        // The same name in both. A kind of absence somebody adds by hand has
        // one name — the one they typed — and putting it only in the German
        // field hides it from every screen that is not in German.
        name_en: draft.name_de.trim(),
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

  const handleRemove = async () => {
    if (!removing) return;
    setIsBusy(true);
    try {
      await hrService.removeAbsenceType(removing.id);
      setRemoving(null);
      await onChanged();
    } catch (failure) {
      // The server refuses to delete a type that absences still point at, which
      // is the right answer — those records would otherwise lose their reason.
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const field = "border-subtle bg-layer-1 text-primary w-full rounded-md border px-3 py-1.5 text-13";

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXL}>
      <div className="flex flex-col gap-4 p-5">
        <div>
          <h3 className="text-14 font-semibold text-primary">{t("hr.absences.types.title")}</h3>
          <p className="text-13 text-tertiary">{t("hr.absences.types.subtitle")}</p>
        </div>

        <div className="overflow-x-auto rounded-md border border-subtle">
          <table className="w-full min-w-[40rem] text-13">
            <thead className="border-b border-subtle text-13 text-placeholder">
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
                  <td colSpan={5} className="px-3 py-6 text-center text-tertiary">
                    {t("hr.absences.types.none_yet")}
                  </td>
                </tr>
              )}
              {types.map((type) => (
                <tr key={type.id} className="border-t border-subtle">
                  <td className="px-3 py-2 text-13 tracking-wide text-secondary tabular-nums">{type.code}</td>
                  <td className="px-3 py-2">
                    <span className={type.is_active ? "text-primary" : "text-tertiary line-through"}>
                      {localName(type, currentLocale)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center text-tertiary">
                    {type.credits_actual ? t("common.yes") : t("common.no")}
                  </td>
                  <td className="px-3 py-2 text-center text-tertiary">
                    {type.consumes_leave_entitlement ? t("common.yes") : t("common.no")}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        className="text-13 text-tertiary hover:text-primary"
                        disabled={isBusy}
                        onClick={() => void handleToggleActive(type)}
                      >
                        {type.is_active ? t("hr.absences.types.retire") : t("hr.absences.types.bring_back")}
                      </button>
                      <button
                        type="button"
                        className="text-tertiary hover:text-danger-primary"
                        aria-label={t("hr.absences.types.delete")}
                        disabled={isBusy}
                        onClick={() => setRemoving(type)}
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

        <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
          <p className="text-13 font-medium text-secondary">{t("hr.absences.types.add")}</p>
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
          <label className="flex items-center gap-2 text-13 text-tertiary">
            <input
              type="checkbox"
              checked={draft.credits_actual}
              onChange={(event) => setDraft({ ...draft, credits_actual: event.target.checked })}
            />
            {t("hr.absences.types.counts_as_worked")}
          </label>
          <label className="flex items-center gap-2 text-13 text-tertiary">
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
              size="lg"
              prependIcon={<Plus />}
              disabled={isBusy || !draft.code.trim() || !draft.name_de.trim()}
              onClick={() => void handleAdd()}
            >
              {t("hr.absences.types.add_button")}
            </Button>
          </div>
        </div>

        <div className="flex items-center justify-end">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("close")}
          </Button>
        </div>
      </div>
      <AlertModalCore
        isOpen={removing !== null}
        handleClose={() => setRemoving(null)}
        handleSubmit={() => void handleRemove()}
        isSubmitting={isBusy}
        variant="danger"
        title={t("hr.absences.types.confirm_remove_title")}
        content={t("hr.absences.types.confirm_remove_body", {
          kind: removing ? localName(removing, currentLocale) : "",
        })}
        primaryButtonText={{
          default: t("hr.absences.types.delete"),
          loading: t("hr.absences.types.deleting"),
        }}
        secondaryButtonText={t("common.cancel")}
      />
    </ModalCore>
  );
};
