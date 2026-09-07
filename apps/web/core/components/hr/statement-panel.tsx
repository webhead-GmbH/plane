/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// services
import { EHrArrangement, EHrRateBasis, HrService } from "@/services/hr.service";
// local imports
import { formatMinutes, tidyAmount } from "./utils";

const hrService = new HrService();

/**
 * The arrangements where the person writes the invoice rather than being paid a
 * salary. Only they have anything to read here.
 */
const INVOICES_OWN_HOURS = new Set<EHrArrangement>([
  EHrArrangement.REMOTE_FULL_TIME_INVOICING,
  EHrArrangement.REMOTE_PART_TIME_INVOICING,
]);

type TProps = {
  periodId: string | null;
  arrangement: EHrArrangement | null;
};

/**
 * What the month comes to, shown before the invoice is written rather than
 * checked after it arrives.
 *
 * Only for the people who invoice their own hours. For everyone else this is a
 * salary question they have no say in, and a panel about amounts on their time
 * page would be noise at best.
 *
 * It says plainly whether the month is settled. An open month still moves, and a
 * figure that quietly changed between being read and being invoiced is exactly
 * the disagreement this is meant to prevent.
 */
export const HrStatementPanel = ({ periodId, arrangement }: TProps) => {
  const { t } = useTranslation();
  const shows = periodId !== null && arrangement !== null && INVOICES_OWN_HOURS.has(arrangement);

  const { data } = useSWR(shows ? `HR_STATEMENT_${periodId}` : null, () =>
    periodId ? hrService.statement(periodId) : null
  );

  if (!shows || !data) return null;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle p-4">
      <div>
        <h2 className="text-13 font-semibold text-primary">{t("hr.statement.title")}</h2>
        <p className="text-13 text-tertiary">{t("hr.statement.hint")}</p>
      </div>

      <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <p className="text-13 text-tertiary">{t("hr.statement.hours")}</p>
          <p className="text-16 font-medium text-primary tabular-nums">{formatMinutes(data.minutes)}</p>
          {/* The decimal form beneath, labelled, because that is what goes on an
              invoice — but it no longer sits alone contradicting the h:mm that
              every other figure in the module is written in. */}
          <p className="text-11 text-tertiary tabular-nums">{t("hr.statement.decimal_hours", { hours: data.hours })}</p>
        </div>

        {data.has_rate ? (
          <>
            <div>
              <p className="text-13 text-tertiary">{t("hr.statement.rate")}</p>
              <p className="text-13 text-secondary tabular-nums">
                {data.rate_basis === EHrRateBasis.HOURLY
                  ? t("hr.rates.per_hour", { amount: tidyAmount(data.hourly_rate), currency: data.currency })
                  : t("hr.statement.monthly_rate")}
              </p>
            </div>

            {data.expected_amount !== null ? (
              <div>
                <p className="text-13 text-tertiary">{t("hr.statement.expected")}</p>
                <p className="text-16 font-medium text-primary tabular-nums">
                  {tidyAmount(data.expected_amount)} {data.currency}
                </p>
              </div>
            ) : null}
          </>
        ) : (
          <p className="text-13 text-tertiary">{t("hr.statement.no_rate")}</p>
        )}
      </div>

      <p className={cn("text-13", data.is_final ? "text-tertiary" : "text-warning-primary")}>
        {data.is_final ? t("hr.statement.settled") : t("hr.statement.still_moving")}
      </p>
    </div>
  );
};
