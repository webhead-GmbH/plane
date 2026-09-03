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
import { tidyAmount } from "./utils";

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
    <div className="border-custom-border-200 flex flex-col gap-3 rounded-md border p-4">
      <div>
        <h2 className="text-custom-text-100 text-sm font-semibold">{t("hr.statement.title")}</h2>
        <p className="text-custom-text-300 text-xs">{t("hr.statement.hint")}</p>
      </div>

      <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <p className="text-custom-text-400 text-xs">{t("hr.statement.hours")}</p>
          <p className="text-custom-text-100 text-lg font-semibold tabular-nums">{data.hours}</p>
        </div>

        {data.has_rate ? (
          <>
            <div>
              <p className="text-custom-text-400 text-xs">{t("hr.statement.rate")}</p>
              <p className="text-custom-text-200 text-sm tabular-nums">
                {data.rate_basis === EHrRateBasis.HOURLY
                  ? t("hr.rates.per_hour", { amount: tidyAmount(data.hourly_rate), currency: data.currency })
                  : t("hr.statement.monthly_rate")}
              </p>
            </div>

            {data.expected_amount !== null ? (
              <div>
                <p className="text-custom-text-400 text-xs">{t("hr.statement.expected")}</p>
                <p className="text-custom-text-100 text-lg font-semibold tabular-nums">
                  {tidyAmount(data.expected_amount)} {data.currency}
                </p>
              </div>
            ) : null}
          </>
        ) : (
          <p className="text-custom-text-300 text-sm">{t("hr.statement.no_rate")}</p>
        )}
      </div>

      <p className={cn("text-xs", data.is_final ? "text-custom-text-400" : "text-amber-600")}>
        {data.is_final ? t("hr.statement.settled") : t("hr.statement.still_moving")}
      </p>
    </div>
  );
};
