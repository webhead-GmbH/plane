/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Download, MoreHorizontal } from "lucide-react";
import { useParams, useSearchParams } from "react-router";
import useSWR from "swr";
// plane imports
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { EmptyStateCompact } from "@plane/blocks/empty-state";
import { Loader } from "@plane/blocks/skeleton";
import { useTranslation } from "@plane/i18n";
// services
import { HrService, type THrMe } from "@/services/hr.service";
// local imports
import { HrManagerPage } from "./hr-manager-only";
import { HrMonthFigures } from "./month-figures";
import { HrPeriodStepper } from "./period-stepper";
import { formatMonthLabel, nextMonth, previousMonth } from "./utils";

const hrService = new HrService();

const toMonthKey = (year: number, month: number) => `${year}-${String(month).padStart(2, "0")}`;

/** The month in the address, or last month, which is the one Team time opens on. */
const monthFromAddress = (value: string | null): [number, number] => {
  if (value && /^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return [Number(value.slice(0, 4)), Number(value.slice(5, 7))];
  const now = new Date();
  return previousMonth(now.getFullYear(), now.getMonth() + 1);
};

/**
 * One person's month, for whoever looks after the team to read.
 *
 * A manager is asked to agree and close a month, and My time only ever shows the
 * signed-in person's own, so without this the only way to read somebody's days
 * would be to sign in as them. Read-only on purpose: agreeing and closing stay on
 * Team time, and changing somebody's hours from here is a separate decision.
 */
export function HrPersonMonthRoot() {
  return (
    <HrManagerPage refused={<PersonMonthUnavailable status={403} />}>
      <PersonMonth />
    </HrManagerPage>
  );
}

function PersonMonth() {
  const { currentLocale } = useTranslation();
  const { profileId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [year, month] = monthFromAddress(searchParams.get("month"));

  const { data, isLoading, error, mutate } = useSWR(`HR_PERSON_MONTH_${profileId}_${year}_${month}`, () =>
    hrService.me(year, month, profileId)
  );

  // The address holds the month, so a link from Team time opens on the month it was on.
  const showMonth = ([nextYear, nextMonthNumber]: [number, number]) =>
    setSearchParams({ month: toMonthKey(nextYear, nextMonthNumber) }, { replace: true });

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <HrPeriodStepper
          label={formatMonthLabel(`${toMonthKey(year, month)}-01`, currentLocale)}
          onPrevious={() => showMonth(previousMonth(year, month))}
          onNext={() => showMonth(nextMonth(year, month))}
        />
        {data?.period ? <PersonMonthMenu periodId={data.period.id} /> : null}
      </div>

      {isLoading && !data ? (
        <Loader className="flex flex-col gap-3">
          <Loader.Item height="96px" />
          <Loader.Item height="320px" />
        </Loader>
      ) : data ? (
        <PersonMonthFigures me={data} />
      ) : (
        <PersonMonthUnavailable status={(error as { status?: number })?.status} onRetry={() => void mutate()} />
      )}
    </div>
  );
}

/** What the person sees on My time, with when they were at work and no way to change anything. */
const PersonMonthFigures = ({ me }: { me: THrMe }) => {
  const { t } = useTranslation();
  const { period, profile, contract } = me;
  const name = profile?.member_display_name ?? "";

  const { data: attendance } = useSWR(
    period && profile ? `HR_MONTH_ATTENDANCE_${profile.id}_${period.period_start}` : null,
    () => hrService.attendanceDays(period?.period_start ?? "", period?.period_end ?? "", profile?.id)
  );

  return (
    <>
      <div className="flex flex-col gap-1">
        <h1 className="text-18 font-medium text-primary">{name}</h1>
        <p className="text-13 text-tertiary">{t("hr.person_month.read_only", { name, page: t("hr.my_time.title") })}</p>
      </div>

      <HrMonthFigures me={me} attendance={attendance} />

      {contract?.records_attendance && attendance?.length === 0 ? (
        <p className="text-13 text-tertiary">{t("hr.person_month.no_attendance")}</p>
      ) : null}
    </>
  );
};

const PersonMonthMenu = ({ periodId }: { periodId: string }) => {
  const { t } = useTranslation();

  return (
    <Menu>
      <MenuTrigger
        render={
          <IconButton
            variant="ghost"
            size="md"
            icon={<Icon icon={MoreHorizontal} />}
            aria-label={t("common.options")}
          />
        }
      />
      <MenuContent side="bottom" align="end">
        <MenuItem
          icon={<Icon icon={Download} />}
          label={t("hr.my_time.export_csv")}
          onClick={() => window.open(hrService.periodExportUrl(periodId, "csv"), "_self")}
        />
        <MenuItem
          icon={<Icon icon={Download} />}
          label={t("hr.my_time.export_excel")}
          onClick={() => window.open(hrService.periodExportUrl(periodId, "xlsx"), "_self")}
        />
      </MenuContent>
    </Menu>
  );
};

const PersonMonthUnavailable = ({ status, onRetry }: { status: number | undefined; onRetry?: () => void }) => {
  const { t } = useTranslation();

  if (status === 403 || status === 404) {
    return (
      <EmptyStateCompact
        title={status === 403 ? t("hr.team_time.not_permitted") : t("hr.person_month.not_found")}
        description={
          status === 403 ? t("hr.team_time.not_permitted_detail", { page: t("hr.my_time.title") }) : undefined
        }
        assetKey="members"
        assetClassName="size-20"
        rootClassName="py-16"
      />
    );
  }

  return (
    <EmptyStateCompact
      title={t("hr.shared.load_failed")}
      description={t("hr.shared.load_failed_detail")}
      assetKey="unknown"
      assetClassName="size-20"
      rootClassName="py-16"
      actions={onRetry ? [{ label: t("hr.shared.retry"), variant: "secondary", onClick: onRetry }] : undefined}
    />
  );
};
