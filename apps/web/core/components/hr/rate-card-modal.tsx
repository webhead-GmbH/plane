/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Trash2 } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { AlertModalCore, EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// services
import { EHrRateBasis, HrService, type THrEmploymentProfile, type THrRateCard } from "@/services/hr.service";
// local imports
import { formatDayWithYear, refusalMessage, tidyAmount } from "./utils";

import { HrRowAction } from "./row-action";

const hrService = new HrService();

const BASES = [EHrRateBasis.HOURLY, EHrRateBasis.MONTHLY_FIXED, EHrRateBasis.MONTHLY_PLUS_OVERTIME];

const BASIS_KEY: Record<number, string> = {
  [EHrRateBasis.HOURLY]: "hourly",
  [EHrRateBasis.MONTHLY_FIXED]: "monthly_fixed",
  [EHrRateBasis.MONTHLY_PLUS_OVERTIME]: "monthly_plus_overtime",
};

type TProps = {
  person: THrEmploymentProfile | null;
  onClose: () => void;
};

/**
 * What somebody's time is worth, and from when.
 *
 * A rate is dated rather than edited, because a month already stated at the old
 * one has to keep meaning what it said. Ending a rate and starting another is
 * how a raise is recorded; changing the figure in place would rewrite every
 * statement that has already gone out.
 *
 * This is what turns a closed month into an amount, so a person with no rate
 * gets a statement that says how many hours and nothing about money. Manager
 * only, in both directions — these are internal cost rates and one person has
 * no business reading another's.
 */
export const HrRateCardModal = ({ person, onClose }: TProps) => {
  const { t, currentLocale } = useTranslation();
  const [validFrom, setValidFrom] = useState("");
  const [basis, setBasis] = useState<EHrRateBasis>(EHrRateBasis.HOURLY);
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [problem, setProblem] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [removing, setRemoving] = useState<THrRateCard | null>(null);

  const { data: rows, mutate } = useSWR(person ? `HR_RATES_${person.id}` : null, () =>
    person ? hrService.rateCards(person.id) : null
  );

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.rates.toasts.refused"),
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.rates.toasts.try_again"),
    });

  const isHourly = basis === EHrRateBasis.HOURLY;

  const handleAdd = async () => {
    if (!person) return;
    if (!validFrom) {
      setProblem(t("hr.rates.errors.date_required"));
      return;
    }
    // Kept as typed and sent as typed. The server holds these as decimals, and
    // rounding a rate on the way there is not something anybody would see.
    const figure = amount.trim().replace(",", ".");
    if (!figure || Number.isNaN(Number(figure)) || Number(figure) < 0) {
      setProblem(t("hr.rates.errors.bad_amount"));
      return;
    }

    setIsBusy(true);
    try {
      await hrService.createRateCard({
        profile: person.id,
        valid_from: validFrom,
        basis,
        currency: currency.trim().toUpperCase() || "EUR",
        hourly_rate: isHourly ? figure : null,
        monthly_amount: isHourly ? null : figure,
      });
      setAmount("");
      setProblem(null);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.rates.toasts.added") });
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
      await hrService.removeRateCard(removing.id);
      await mutate();
      setRemoving(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.rates.toasts.removed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const rates = rows ?? [];

  return (
    <ModalCore isOpen={person !== null} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXXL}>
      <div className="flex max-h-[80vh] flex-col gap-4 overflow-y-auto p-5">
        <div>
          <h3 className="text-16 font-medium text-primary">
            {t("hr.rates.title", { person: person?.member_display_name || person?.member_email || "" })}
          </h3>
          <p className="text-13 text-tertiary">{t("hr.rates.hint")}</p>
        </div>

        {rates.length === 0 ? (
          <p className="text-13 text-tertiary">{t("hr.rates.none_yet")}</p>
        ) : (
          <div className="divide-y divide-subtle rounded-md border border-subtle">
            {rates.map((row) => (
              <div key={row.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
                <span className="text-13 text-primary tabular-nums">
                  {row.basis === EHrRateBasis.HOURLY
                    ? t("hr.rates.per_hour", { amount: tidyAmount(row.hourly_rate), currency: row.currency })
                    : t("hr.rates.per_month", { amount: tidyAmount(row.monthly_amount), currency: row.currency })}
                </span>
                <span className="rounded bg-layer-2 px-1.5 py-0.5 text-13 text-tertiary">
                  {t(`hr.rates.basis.${BASIS_KEY[row.basis]}`)}
                </span>
                <span className="flex-1 text-13 text-tertiary">
                  {row.valid_to
                    ? t("hr.rates.between", {
                        from: formatDayWithYear(row.valid_from, currentLocale),
                        to: formatDayWithYear(row.valid_to, currentLocale),
                      })
                    : t("hr.rates.from", { date: formatDayWithYear(row.valid_from, currentLocale) })}
                </span>
                <HrRowAction
                  icon={<Trash2 className="size-4" />}
                  label={t("hr.rates.remove")}
                  subject={person?.member_display_name || person?.member_email || ""}
                  danger
                  disabled={isBusy}
                  onClick={() => setRemoving(row)}
                />
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
          <p className="text-13 font-medium text-secondary">{t("hr.rates.add")}</p>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="text-13 text-tertiary" htmlFor="hr-rate-from">
                {t("hr.rates.valid_from")}
              </label>
              <input
                id="hr-rate-from"
                type="date"
                value={validFrom}
                onChange={(event) => setValidFrom(event.target.value)}
                className="w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
              />
            </div>

            <div>
              <label className="text-13 text-tertiary" htmlFor="hr-rate-basis">
                {t("hr.rates.basis_label")}
              </label>
              <select
                id="hr-rate-basis"
                value={basis}
                onChange={(event) => setBasis(Number(event.target.value) as EHrRateBasis)}
                className="w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
              >
                {BASES.map((option) => (
                  <option key={option} value={option}>
                    {t(`hr.rates.basis.${BASIS_KEY[option]}`)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-13 text-tertiary" htmlFor="hr-rate-amount">
                {isHourly ? t("hr.rates.hourly_rate") : t("hr.rates.monthly_amount")}
              </label>
              <input
                id="hr-rate-amount"
                type="text"
                inputMode="decimal"
                value={amount}
                placeholder={t("hr.rates.amount_placeholder")}
                onChange={(event) => setAmount(event.target.value)}
                className="w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
              />
            </div>

            <div>
              <label className="text-13 text-tertiary" htmlFor="hr-rate-currency">
                {t("hr.rates.currency")}
              </label>
              <input
                id="hr-rate-currency"
                type="text"
                maxLength={3}
                value={currency}
                onChange={(event) => setCurrency(event.target.value)}
                className="w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary uppercase"
              />
            </div>
          </div>

          {problem && (
            <p role="alert" className="text-13 text-danger-primary">
              {problem}
            </p>
          )}

          <div className="flex justify-end">
            <Button variant="primary" size="lg" loading={isBusy} onClick={() => void handleAdd()}>
              {t("hr.rates.add_button")}
            </Button>
          </div>
        </div>

        <div className="flex justify-end">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("hr.rates.close")}
          </Button>
        </div>
      </div>

      <AlertModalCore
        isOpen={removing !== null}
        handleClose={() => setRemoving(null)}
        handleSubmit={() => void handleRemove()}
        isSubmitting={isBusy}
        variant="danger"
        title={t("hr.rates.confirm_remove_title")}
        content={t("hr.rates.confirm_remove_body")}
        primaryButtonText={{ default: t("hr.rates.remove"), loading: t("hr.rates.removing") }}
        secondaryButtonText={t("common.cancel")}
      />
    </ModalCore>
  );
};
