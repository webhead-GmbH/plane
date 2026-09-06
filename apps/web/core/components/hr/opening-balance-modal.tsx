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
import { cn } from "@plane/utils";
// services
import {
  EHrBalanceKind,
  EHrConfidence,
  HrService,
  type THrEmploymentProfile,
  type THrOpeningBalance,
} from "@/services/hr.service";
// local imports
import { balanceTone, formatBalance, formatDayLabel, parseDuration, refusalMessage } from "./utils";

const hrService = new HrService();

const KINDS = [EHrBalanceKind.TIME_BALANCE, EHrBalanceKind.LEAVE, EHrBalanceKind.OVERTIME_BANK];
const CONFIDENCES = [EHrConfidence.EXACT, EHrConfidence.RECONSTRUCTED, EHrConfidence.ESTIMATED, EHrConfidence.AGREED];

const KIND_KEY: Record<number, string> = {
  [EHrBalanceKind.TIME_BALANCE]: "time_balance",
  [EHrBalanceKind.LEAVE]: "leave",
  [EHrBalanceKind.OVERTIME_BANK]: "overtime_bank",
};

const CONFIDENCE_KEY: Record<number, string> = {
  [EHrConfidence.EXACT]: "exact",
  [EHrConfidence.RECONSTRUCTED]: "reconstructed",
  [EHrConfidence.ESTIMATED]: "estimated",
  [EHrConfidence.AGREED]: "agreed",
};

type TProps = {
  person: THrEmploymentProfile | null;
  /** True when the viewer is looking at their own, and so may agree it. */
  isOwn: boolean;
  canRecord: boolean;
  onClose: () => void;
};

/**
 * Where somebody stood on the day this started counting for them.
 *
 * These figures are agreed rather than worked out. There is no history here to
 * derive them from — that is the whole reason they exist — so the record keeps
 * what the number was based on and how much anyone can stand behind it, and the
 * person it belongs to says whether they accept it.
 *
 * Nothing is edited. A correction is a new figure pointing at the one it
 * replaces, because a starting balance that quietly changed is one nobody can
 * argue about afterwards.
 */
export const HrOpeningBalanceModal = ({ person, isOwn, canRecord, onClose }: TProps) => {
  const { t } = useTranslation();
  const [amount, setAmount] = useState("");
  const [kind, setKind] = useState<EHrBalanceKind>(EHrBalanceKind.TIME_BALANCE);
  const [confidence, setConfidence] = useState<EHrConfidence>(EHrConfidence.AGREED);
  const [effectiveOn, setEffectiveOn] = useState("");
  const [basis, setBasis] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const { data: rows, mutate } = useSWR(person ? `HR_OPENING_${person.id}` : null, () =>
    person ? hrService.openingBalances(person.id) : null
  );

  useEffect(() => {
    if (!person) return;
    setAmount("");
    setKind(EHrBalanceKind.TIME_BALANCE);
    setConfidence(EHrConfidence.AGREED);
    setEffectiveOn(person.hire_date ?? "");
    setBasis("");
    setProblem(null);
  }, [person]);

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.opening.toasts.refused"),
      message: refusalMessage(failure) ?? t("hr.opening.toasts.try_again"),
    });

  const handleRecord = async () => {
    if (!person) return;
    // A negative balance is the normal case here, so the sign has to survive.
    const negative = amount.trim().startsWith("-");
    const size = parseDuration(amount.replace("-", ""));
    if (size === null) {
      setProblem(t("hr.opening.errors.bad_duration"));
      return;
    }
    if (!basis.trim()) {
      setProblem(t("hr.opening.errors.basis_required"));
      return;
    }
    if (!effectiveOn) {
      setProblem(t("hr.opening.errors.date_required"));
      return;
    }
    setIsBusy(true);
    try {
      await hrService.recordOpeningBalance(person.id, {
        effective_on: effectiveOn,
        kind,
        minutes: negative ? -size : size,
        confidence,
        basis: basis.trim(),
      });
      setAmount("");
      setBasis("");
      setProblem(null);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.opening.toasts.recorded") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleAgree = async (row: THrOpeningBalance) => {
    if (!person) return;
    setIsBusy(true);
    try {
      await hrService.agreeOpeningBalance(person.id, row.id);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.opening.toasts.agreed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const current = (rows ?? []).filter((row) => row.superseded_by === null);
  const replaced = (rows ?? []).filter((row) => row.superseded_by !== null);

  return (
    <ModalCore isOpen={person !== null} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXXL}>
      <div className="flex max-h-[80vh] flex-col gap-4 overflow-y-auto p-5">
        <div>
          <h3 className="text-custom-text-100 text-lg font-medium">
            {t("hr.opening.title", { person: person?.member_display_name || person?.member_email || "" })}
          </h3>
          <p className="text-custom-text-300 text-sm">{t("hr.opening.hint")}</p>
        </div>

        {current.length === 0 ? (
          <p className="text-custom-text-400 text-sm">{t("hr.opening.none_yet")}</p>
        ) : (
          <div className="border-custom-border-200 divide-custom-border-100 divide-y rounded-md border">
            {current.map((row) => (
              <div key={row.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
                <span className={cn("text-sm w-20 tabular-nums", balanceTone(row.minutes))}>
                  {formatBalance(row.minutes)}
                </span>
                <span className="text-custom-text-200 text-sm">{t(`hr.opening.kind.${KIND_KEY[row.kind]}`)}</span>
                <span className="text-custom-text-400 text-xs">
                  {t("hr.opening.from", { date: formatDayLabel(row.effective_on) })}
                </span>
                <span className="bg-custom-background-80 text-custom-text-300 text-xs rounded px-1.5 py-0.5">
                  {t(`hr.opening.confidence.${CONFIDENCE_KEY[row.confidence]}`)}
                </span>
                <span className="text-custom-text-400 text-xs flex-1 truncate">{row.basis}</span>
                {row.acknowledged_at ? (
                  <span className="text-xs text-green-600 flex items-center gap-1">
                    <Check className="size-3.5" />
                    {t("hr.opening.agreed")}
                  </span>
                ) : isOwn ? (
                  <Button variant="link" size="sm" loading={isBusy} onClick={() => void handleAgree(row)}>
                    {t("hr.opening.agree")}
                  </Button>
                ) : (
                  <span className="text-xs text-amber-600">{t("hr.opening.not_agreed")}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {replaced.length > 0 ? (
          <details className="text-custom-text-400 text-xs">
            <summary className="cursor-pointer">{t("hr.opening.replaced", { count: replaced.length })}</summary>
            <div className="mt-2 flex flex-col gap-1">
              {replaced.map((row) => (
                <span key={row.id} className="tabular-nums">
                  {formatBalance(row.minutes)} · {formatDayLabel(row.effective_on)} · {row.basis}
                </span>
              ))}
            </div>
          </details>
        ) : null}

        {canRecord ? (
          <div className="border-custom-border-200 flex flex-col gap-3 rounded-md border p-3">
            <p className="text-custom-text-200 text-sm font-medium">{t("hr.opening.record")}</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label={t("hr.opening.amount")}>
                <input
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="-12:30"
                  className={cn(inputClass, "tabular-nums")}
                />
              </Field>
              <Field label={t("hr.opening.what_for")}>
                <select
                  value={kind}
                  onChange={(e) => setKind(Number(e.target.value) as EHrBalanceKind)}
                  className={inputClass}
                >
                  {KINDS.map((value) => (
                    <option key={value} value={value}>
                      {t(`hr.opening.kind.${KIND_KEY[value]}`)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t("hr.opening.from_label")}>
                <input
                  type="date"
                  value={effectiveOn}
                  onChange={(e) => setEffectiveOn(e.target.value)}
                  className={inputClass}
                />
              </Field>
              <Field label={t("hr.opening.how_sure")}>
                <select
                  value={confidence}
                  onChange={(e) => setConfidence(Number(e.target.value) as EHrConfidence)}
                  className={inputClass}
                >
                  {CONFIDENCES.map((value) => (
                    <option key={value} value={value}>
                      {t(`hr.opening.confidence.${CONFIDENCE_KEY[value]}`)}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label={t("hr.opening.basis")}>
              <input
                value={basis}
                onChange={(e) => setBasis(e.target.value)}
                placeholder={t("hr.opening.basis_placeholder")}
                className={inputClass}
              />
            </Field>
            {problem ? <p className="text-sm text-red-500">{problem}</p> : null}
            <div className="flex justify-end">
              <Button variant="primary" size="sm" loading={isBusy} onClick={() => void handleRecord()}>
                {t("hr.opening.record_confirm")}
              </Button>
            </div>
          </div>
        ) : null}

        <div className="flex items-center justify-end">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("hr.opening.done")}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
};

const inputClass =
  "border-custom-border-200 bg-custom-background-100 text-custom-text-100 focus:border-custom-primary-100 w-full rounded-md border px-3 py-1.5 text-sm outline-none";

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="flex flex-col gap-1">
    <span className="text-custom-text-300 text-xs font-medium">{label}</span>
    {children}
  </label>
);
