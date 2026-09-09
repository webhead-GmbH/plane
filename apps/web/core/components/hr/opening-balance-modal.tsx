/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useId, useReducer, useState } from "react";
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

type TTranslate = (key: string, values?: Record<string, unknown>) => string;

/** Whoever this is, by whichever of their names the record actually carries. */
const personName = (person: THrEmploymentProfile | null) => person?.member_display_name || person?.member_email || "";

const complain = (failure: unknown, t: TTranslate, locale: string) =>
  setToast({
    type: TOAST_TYPE.ERROR,
    title: t("hr.opening.toasts.refused"),
    message: refusalMessage(failure, t, locale) ?? t("hr.opening.toasts.try_again"),
  });

/**
 * The figure being written down: a first one, or the replacement for one.
 *
 * A correction arrives whole — it is the row it replaces, with something about
 * it changed — and it leaves whole, whether it was filed or given up on. So
 * this is one thing rather than a handful of fields to be kept in step.
 */
type TDraft = {
  amount: string;
  kind: EHrBalanceKind;
  confidence: EHrConfidence;
  effectiveOn: string;
  basis: string;
  problem: string | null;
  /** The figure being replaced, where this is a correction rather than a first entry. */
  correcting: THrOpeningBalance | null;
};

type TDraftAction =
  | { type: "typed"; changes: Partial<TDraft> }
  | { type: "correct"; row: THrOpeningBalance }
  | { type: "abandon" }
  | { type: "refused"; problem: string }
  | { type: "filed" };

/**
 * Seeded once, at the moment this dialog is built. Both callers key it on the
 * person, so a different person is a different dialog and there is nothing to
 * reset afterwards.
 */
const startingDraft = (person: THrEmploymentProfile | null): TDraft => ({
  amount: "",
  kind: EHrBalanceKind.TIME_BALANCE,
  confidence: EHrConfidence.AGREED,
  effectiveOn: person?.hire_date ?? "",
  basis: "",
  problem: null,
  correcting: null,
});

const draftReducer = (draft: TDraft, action: TDraftAction): TDraft => {
  // A correction starts as everything the replaced figure said, so that the one
  // thing somebody came here to change is the only thing they have to type.
  if (action.type === "correct")
    return {
      ...draft,
      correcting: action.row,
      kind: action.row.kind,
      effectiveOn: action.row.effective_on,
      // formatBalance adds a leading "+", which the parser reads as part of the
      // number and refuses.
      amount: formatMinutes(action.row.minutes),
      confidence: action.row.confidence,
      basis: action.row.basis,
    };
  // Giving up on a correction and filing one leave the same empty form behind.
  if (action.type === "abandon" || action.type === "filed")
    return { ...draft, correcting: null, amount: "", basis: "", problem: null };
  if (action.type === "refused") return { ...draft, problem: action.problem };
  return { ...draft, ...action.changes };
};

/**
 * The figure as it was typed, or the first thing wrong with it.
 *
 * A negative balance is the normal case here, so the sign has to survive.
 */
const readDraft = (draft: TDraft, t: TTranslate): { minutes: number } | { problem: string } => {
  const negative = draft.amount.trim().startsWith("-");
  const size = parseDuration(draft.amount.replace("-", ""));
  if (size === null) return { problem: t("hr.opening.errors.bad_duration") };
  if (!draft.basis.trim()) return { problem: t("hr.opening.errors.basis_required") };
  if (!draft.effectiveOn) return { problem: t("hr.opening.errors.date_required") };
  return { minutes: negative ? -size : size };
};

/**
 * A correction replaces one particular figure, so its date and kind come from
 * the row being corrected — the server reads them from there and ignores
 * anything sent. Sending them anyway meant the two fields could be changed on
 * screen and silently have no effect.
 */
const balancePayload = (draft: TDraft, minutes: number) =>
  draft.correcting
    ? { minutes, confidence: draft.confidence, basis: draft.basis.trim() }
    : {
        effective_on: draft.effectiveOn,
        kind: draft.kind,
        minutes,
        confidence: draft.confidence,
        basis: draft.basis.trim(),
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
  const [draft, dispatch] = useReducer(draftReducer, person, startingDraft);
  const [isBusy, setIsBusy] = useState(false);
  const [agreeing, setAgreeing] = useState<THrOpeningBalance | null>(null);

  const { data: rows, mutate } = useSWR(person ? `HR_OPENING_${person.id}` : null, () =>
    person ? hrService.openingBalances(person.id) : null
  );

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
      complain(failure, t, currentLocale);
    } finally {
      setIsBusy(false);
    }
  };

  const balances = rows ?? [];
  const current = balances.filter((row) => row.superseded_by === null);
  const replaced = balances.filter((row) => row.superseded_by !== null);

  return (
    <ModalCore isOpen={person !== null} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXXL}>
      <div className="flex max-h-[80vh] flex-col gap-4 overflow-y-auto p-5">
        <div>
          <h3 className="text-16 font-medium text-primary">{t("hr.opening.title", { person: personName(person) })}</h3>
          <p className="text-13 text-tertiary">{t("hr.opening.hint")}</p>
        </div>

        <CurrentBalances
          rows={current}
          isOwn={isOwn}
          isBusy={isBusy}
          onCorrect={(row) => dispatch({ type: "correct", row })}
          onAgree={setAgreeing}
        />

        <ReplacedBalances rows={replaced} />

        {canRecord ? (
          <RecordBalanceForm
            person={person}
            draft={draft}
            dispatch={dispatch}
            isBusy={isBusy}
            onBusyChange={setIsBusy}
            onRecorded={mutate}
          />
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
        secondaryButtonText={t("common.cancel")}
      />
    </ModalCore>
  );
};

type TListProps = {
  rows: THrOpeningBalance[];
  isOwn: boolean;
  isBusy: boolean;
  onCorrect: (row: THrOpeningBalance) => void;
  onAgree: (row: THrOpeningBalance) => void;
};

/** The figures that still stand. */
const CurrentBalances = ({ rows, isOwn, isBusy, onCorrect, onAgree }: TListProps) => {
  const { t } = useTranslation();

  if (rows.length === 0) return <p className="text-13 text-tertiary">{t("hr.opening.none_yet")}</p>;

  return (
    <div className="divide-y divide-subtle rounded-md border border-subtle">
      {rows.map((row) => (
        <OpeningBalanceRow
          key={row.id}
          row={row}
          isOwn={isOwn}
          isBusy={isBusy}
          onCorrect={onCorrect}
          onAgree={onAgree}
        />
      ))}
    </div>
  );
};

type TRowProps = {
  row: THrOpeningBalance;
  isOwn: boolean;
  isBusy: boolean;
  onCorrect: (row: THrOpeningBalance) => void;
  onAgree: (row: THrOpeningBalance) => void;
};

/**
 * One figure, and what is left to do about it: a manager may still correct it
 * while it is unagreed, and the person it belongs to is the only one who can
 * say they accept it.
 */
const OpeningBalanceRow = ({ row, isOwn, isBusy, onCorrect, onAgree }: TRowProps) => {
  const { t, currentLocale } = useTranslation();

  return (
    <div className="flex flex-wrap items-center gap-3 px-3 py-2">
      <span className={cn("w-20 text-13 tabular-nums", balanceTone(row.minutes))}>{formatBalance(row.minutes)}</span>
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
          onClick={() => onCorrect(row)}
        />
      ) : null}
      {row.acknowledged_at ? (
        <span className="flex items-center gap-1 text-13 text-success-primary">
          <Check className="size-3.5" />
          {t("hr.opening.agreed")}
        </span>
      ) : isOwn ? (
        <Button variant="secondary" size="lg" loading={isBusy} onClick={() => onAgree(row)}>
          {t("hr.opening.agree")}
        </Button>
      ) : (
        <span className="text-13 text-warning-primary">{t("hr.opening.not_agreed")}</span>
      )}
    </div>
  );
};

/** What earlier corrections replaced, kept where it can be looked at but not read first. */
const ReplacedBalances = ({ rows }: { rows: THrOpeningBalance[] }) => {
  const { t, currentLocale } = useTranslation();

  if (rows.length === 0) return null;

  return (
    <details className="text-13 text-tertiary">
      <summary className="cursor-pointer">{t("hr.opening.replaced", { count: rows.length })}</summary>
      <div className="mt-2 flex flex-col gap-1">
        {rows.map((row) => (
          <span key={row.id} className="tabular-nums">
            {formatBalance(row.minutes)} · {formatDayWithYear(row.effective_on, currentLocale)} · {row.basis}
          </span>
        ))}
      </div>
    </details>
  );
};

type TFormProps = {
  person: THrEmploymentProfile | null;
  draft: TDraft;
  dispatch: React.Dispatch<TDraftAction>;
  isBusy: boolean;
  onBusyChange: (busy: boolean) => void;
  onRecorded: () => Promise<unknown>;
};

const RecordBalanceForm = ({ person, draft, dispatch, isBusy, onBusyChange, onRecorded }: TFormProps) => {
  const { t, currentLocale } = useTranslation();
  const basisId = useId();
  const { correcting, problem } = draft;

  const handleRecord = async () => {
    if (!person) return;
    const typed = readDraft(draft, t);
    if ("problem" in typed) {
      dispatch({ type: "refused", problem: typed.problem });
      return;
    }
    onBusyChange(true);
    try {
      const payload = balancePayload(draft, typed.minutes);
      // Correcting supersedes the figure it replaces. Recording a second one of
      // the same kind instead would leave two rows both reading as current, and
      // the month would quietly count only one of them.
      if (correcting) await hrService.correctOpeningBalance(person.id, correcting.id, payload);
      else await hrService.recordOpeningBalance(person.id, payload);
      dispatch({ type: "filed" });
      await onRecorded();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.opening.toasts.recorded") });
    } catch (failure) {
      complain(failure, t, currentLocale);
    } finally {
      onBusyChange(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-13 font-medium text-secondary">
          {correcting ? t("hr.opening.correcting_heading") : t("hr.opening.record")}
        </p>
        {correcting ? (
          <Button variant="link" size="lg" onClick={() => dispatch({ type: "abandon" })}>
            {t("hr.opening.stop_correcting")}
          </Button>
        ) : null}
      </div>
      <BalanceFields draft={draft} dispatch={dispatch} />
      <Field label={t("hr.opening.basis")} htmlFor={basisId}>
        <input
          id={basisId}
          value={draft.basis}
          onChange={(e) => dispatch({ type: "typed", changes: { basis: e.target.value } })}
          placeholder={t("hr.opening.basis_placeholder")}
          className={inputClass}
        />
      </Field>
      {problem ? (
        <p role="alert" className="text-13 text-danger-primary">
          {problem}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button variant="primary" size="lg" loading={isBusy} onClick={() => void handleRecord()}>
          {correcting ? t("hr.opening.correct_confirm") : t("hr.opening.record_confirm")}
        </Button>
      </div>
    </div>
  );
};

/** How much, of what, from when, and how sure anyone is of it. */
const BalanceFields = ({ draft, dispatch }: { draft: TDraft; dispatch: React.Dispatch<TDraftAction> }) => {
  const { t } = useTranslation();
  const amountId = useId();
  const isCorrecting = draft.correcting !== null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Field label={t("hr.opening.amount")} htmlFor={amountId}>
        <input
          id={amountId}
          value={draft.amount}
          onChange={(e) => dispatch({ type: "typed", changes: { amount: e.target.value } })}
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
          value={draft.kind}
          onChange={(e) => dispatch({ type: "typed", changes: { kind: Number(e.target.value) as EHrBalanceKind } })}
          disabled={isCorrecting}
          className={cn(inputClass, isCorrecting && "text-tertiary")}
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
          value={draft.effectiveOn}
          onChange={(e) => dispatch({ type: "typed", changes: { effectiveOn: e.target.value } })}
          disabled={isCorrecting}
          className={cn(inputClass, isCorrecting && "text-tertiary")}
        />
      </Field>
      <Field label={t("hr.opening.how_sure")}>
        <select
          value={draft.confidence}
          onChange={(e) =>
            dispatch({ type: "typed", changes: { confidence: Number(e.target.value) as EHrConfidence } })
          }
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
  );
};

const inputClass =
  "border-subtle bg-layer-1 text-primary focus:border-accent-strong w-full rounded-md border px-3 py-1.5 text-13 outline-none";

const Field = ({ label, htmlFor, children }: { label: string; htmlFor?: string; children: React.ReactNode }) => (
  <label className="flex flex-col gap-1" htmlFor={htmlFor}>
    <span className="text-13 font-medium text-tertiary">{label}</span>
    {children}
  </label>
);
