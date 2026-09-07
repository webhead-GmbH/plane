/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { Check, Pencil } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { AlertModalCore, EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
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
import { balanceTone, formatBalance, formatDayWithYear, formatMinutes, parseDuration, refusalMessage } from "./utils";

import { HrRowAction } from "./row-action";

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
  const { t, currentLocale } = useTranslation();
  const [amount, setAmount] = useState("");
  const [kind, setKind] = useState<EHrBalanceKind>(EHrBalanceKind.TIME_BALANCE);
  const [confidence, setConfidence] = useState<EHrConfidence>(EHrConfidence.AGREED);
  const [effectiveOn, setEffectiveOn] = useState("");
  const [basis, setBasis] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [agreeing, setAgreeing] = useState<THrOpeningBalance | null>(null);
  const [correcting, setCorrecting] = useState<THrOpeningBalance | null>(null);

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
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.opening.toasts.try_again"),
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
      // A correction replaces one particular figure, so its date and kind come
      // from the row being corrected — the server reads them from there and
      // ignores anything sent. Sending them anyway meant the two fields could be
      // changed on screen and silently have no effect.
      const payload = correcting
        ? { minutes: negative ? -size : size, confidence, basis: basis.trim() }
        : {
            effective_on: effectiveOn,
            kind,
            minutes: negative ? -size : size,
            confidence,
            basis: basis.trim(),
          };
      // Correcting supersedes the figure it replaces. Recording a second one of
      // the same kind instead would leave two rows both reading as current, and
      // the month would quietly count only one of them.
      if (correcting) await hrService.correctOpeningBalance(person.id, correcting.id, payload);
      else await hrService.recordOpeningBalance(person.id, payload);
      setAmount("");
      setBasis("");
      setProblem(null);
      setCorrecting(null);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.opening.toasts.recorded") });
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
      await hrService.agreeOpeningBalance(person.id, row.id);
      await mutate();
      setAgreeing(null);
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
          <h3 className="text-16 font-medium text-primary">
            {t("hr.opening.title", { person: person?.member_display_name || person?.member_email || "" })}
          </h3>
          <p className="text-13 text-tertiary">{t("hr.opening.hint")}</p>
        </div>

        {current.length === 0 ? (
          <p className="text-13 text-tertiary">{t("hr.opening.none_yet")}</p>
        ) : (
          <div className="divide-y divide-subtle rounded-md border border-subtle">
            {current.map((row) => (
              <div key={row.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
                <span className={cn("w-20 text-13 tabular-nums", balanceTone(row.minutes))}>
                  {formatBalance(row.minutes)}
                </span>
                <span className="text-13 text-secondary">{t(`hr.opening.kind.${KIND_KEY[row.kind]}`)}</span>
                <span className="text-13 text-tertiary">
                  {t("hr.opening.from", { date: formatDayWithYear(row.effective_on, currentLocale) })}
                </span>
                <span className="rounded bg-layer-2 px-1.5 py-0.5 text-13 text-tertiary">
                  {t(`hr.opening.confidence.${CONFIDENCE_KEY[row.confidence]}`)}
                </span>
                <span className="flex-1 truncate text-13 text-tertiary">{row.basis}</span>
                {!isOwn && !row.acknowledged_at ? (
                  <HrRowAction
                    icon={<Pencil className="size-4" />}
                    label={t("hr.opening.correct")}
                    disabled={isBusy}
                    onClick={() => {
                      setCorrecting(row);
                      setKind(row.kind);
                      setEffectiveOn(row.effective_on);
                      // formatBalance adds a leading "+", which the parser reads
                      // as part of the number and refuses.
                      setAmount(formatMinutes(row.minutes));
                      setConfidence(row.confidence);
                      setBasis(row.basis);
                    }}
                  />
                ) : null}
                {row.acknowledged_at ? (
                  <span className="flex items-center gap-1 text-13 text-success-primary">
                    <Check className="size-3.5" />
                    {t("hr.opening.agreed")}
                  </span>
                ) : isOwn ? (
                  <Button variant="secondary" size="lg" loading={isBusy} onClick={() => setAgreeing(row)}>
                    {t("hr.opening.agree")}
                  </Button>
                ) : (
                  <span className="text-13 text-warning-primary">{t("hr.opening.not_agreed")}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {replaced.length > 0 ? (
          <details className="text-13 text-tertiary">
            <summary className="cursor-pointer">{t("hr.opening.replaced", { count: replaced.length })}</summary>
            <div className="mt-2 flex flex-col gap-1">
              {replaced.map((row) => (
                <span key={row.id} className="tabular-nums">
                  {formatBalance(row.minutes)} · {formatDayWithYear(row.effective_on, currentLocale)} · {row.basis}
                </span>
              ))}
            </div>
          </details>
        ) : null}

        {canRecord ? (
          <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-13 font-medium text-secondary">
                {correcting ? t("hr.opening.correcting_heading") : t("hr.opening.record")}
              </p>
              {correcting ? (
                <Button
                  variant="link"
                  size="lg"
                  onClick={() => {
                    setCorrecting(null);
                    setAmount("");
                    setBasis("");
                    setProblem(null);
                  }}
                >
                  {t("hr.opening.stop_correcting")}
                </Button>
              ) : null}
            </div>
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
                {/* Fixed while correcting: these say which figure is being
                    replaced, and the replacement is that figure or it is a
                    different balance entirely. Shown rather than hidden, because
                    what is being corrected is the thing worth being sure of. */}
                <select
                  value={kind}
                  onChange={(e) => setKind(Number(e.target.value) as EHrBalanceKind)}
                  disabled={correcting !== null}
                  className={cn(inputClass, correcting && "text-tertiary")}
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
                  disabled={correcting !== null}
                  className={cn(inputClass, correcting && "text-tertiary")}
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
            {problem ? <p className="text-13 text-danger-primary">{problem}</p> : null}
            <div className="flex justify-end">
              <Button variant="primary" size="lg" loading={isBusy} onClick={() => void handleRecord()}>
                {correcting ? t("hr.opening.correct_confirm") : t("hr.opening.record_confirm")}
              </Button>
            </div>
          </div>
        ) : null}

        <div className="flex items-center justify-end">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("hr.opening.done")}
          </Button>
        </div>
      </div>

      <AlertModalCore
        isOpen={agreeing !== null}
        handleClose={() => setAgreeing(null)}
        handleSubmit={() => void handleAgree()}
        isSubmitting={isBusy}
        variant="primary"
        title={t("hr.opening.confirm_agree_title")}
        content={t("hr.opening.confirm_agree_body", {
          amount: agreeing ? formatBalance(agreeing.minutes) : "",
        })}
        primaryButtonText={{ default: t("hr.opening.agree"), loading: t("hr.opening.agreeing") }}
      />
    </ModalCore>
  );
};

const inputClass =
  "border-subtle bg-layer-1 text-primary focus:border-accent-strong w-full rounded-md border px-3 py-1.5 text-13 outline-none";

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="flex flex-col gap-1">
    <span className="text-13 font-medium text-tertiary">{label}</span>
    {children}
  </label>
);
