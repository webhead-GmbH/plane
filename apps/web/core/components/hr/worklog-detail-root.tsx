/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { AlertTriangle, ChevronDown, ChevronRight, Timer } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { Loader, Tooltip } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import {
  EHrTimeCategory,
  HrService,
  type THrWorklogGroup,
  type THrWorklogGrouping,
  type THrWorklogRow,
} from "@/services/hr.service";
// local imports
import { HrFigure } from "./figure";
import { HrPeriodStepper } from "./period-stepper";
import { formatDayLabel, formatDayWithYear, formatMinutes, formatMonthLabel, nextMonth, previousMonth } from "./utils";

const hrService = new HrService();

const GROUPINGS: THrWorklogGrouping[] = ["day", "work_item", "project", "week", "workspace"];

const CATEGORY_KEY: Record<number, string> = {
  [EHrTimeCategory.MEETING]: "meeting",
  [EHrTimeCategory.TRAINING]: "training",
  [EHrTimeCategory.ADMIN]: "admin",
  [EHrTimeCategory.TRAVEL]: "travel",
  [EHrTimeCategory.ON_CALL]: "on_call",
  [EHrTimeCategory.CORRECTION]: "correction",
  [EHrTimeCategory.IMPORTED]: "imported",
};

/**
 * Raw seconds for one row, so a single entry never claims a rounded figure.
 *
 * Under a minute is said in words rather than shown as `0:00`. The seconds are
 * real — they are summed with the rest of the day before anything is rounded —
 * and a zero beside a non-zero subtotal reads as a bug rather than as a short
 * entry.
 */
const useRowDuration = () => {
  const { t } = useTranslation();
  return (seconds: number | null) => {
    if (seconds === null) return "—";
    if (seconds > 0 && seconds < 30) return t("hr.detail.under_a_minute");
    return formatMinutes(Math.round(seconds / 60));
  };
};

/**
 * Where a month's hours went, entry by entry.
 *
 * The month has only ever shown one number a day. That answers "how much" and
 * leaves the question it invites — on what — with nowhere to be asked, so the
 * only way to check a figure was to open every work item in turn.
 *
 * Grouping is the whole point rather than a decoration: the same hours read as
 * a week's shape, as a list of work items, or as which project took the month,
 * and which of those a person needs depends entirely on why they are looking.
 */
export const HrWorklogDetailRoot = observer(function HrWorklogDetailRoot() {
  const { t, currentLocale } = useTranslation();
  const now = new Date();
  const [[year, month], setMonth] = useState<[number, number]>([now.getFullYear(), now.getMonth() + 1]);
  const [grouping, setGrouping] = useState<THrWorklogGrouping>("day");
  const [personId, setPersonId] = useState("");
  const [opened, setOpened] = useState<Record<string, boolean>>({});

  const { data: me, isLoading: loadingMe, error: meError } = useSWR("HR_ME_ROLE", () => hrService.me());
  const isManager = Boolean(me?.is_hr_manager);
  const { data: people } = useSWR(isManager ? "HR_EMPLOYEES" : null, () => hrService.employees());

  // Whoever is being looked at: the person picked, or the reader themselves.
  const subjectId = personId || me?.profile?.id || "";

  const { data, isLoading, error, mutate } = useSWR(
    subjectId ? `HR_WORKLOG_DETAIL_${subjectId}_${year}_${month}_${grouping}` : null,
    () => (subjectId ? hrService.worklogDetail(subjectId, year, month, grouping) : null),
    // The month, the person and the grouping are all in the key, so changing any
    // of them would otherwise empty the table and unmount the very control that
    // was just used — taking the keyboard focus, or the button under the cursor,
    // with it.
    { keepPreviousData: true }
  );

  const monthLabel = formatMonthLabel(`${year}-${String(month).padStart(2, "0")}-01`, currentLocale);
  const refusal = (error ?? meError) as { status?: number } | undefined;
  const notAllowed = refusal?.status === 403;

  const groupLabel = (row: THrWorklogGroup) => {
    if (grouping === "day") return formatDayLabel(row.first_day, currentLocale);
    if (grouping === "week") return t("hr.detail.week_of", { date: formatDayWithYear(row.first_day, currentLocale) });
    return row.label || t("hr.detail.unnamed");
  };

  if ((isLoading || loadingMe) && !data)
    return (
      <Loader className="flex w-full flex-col gap-3">
        <Loader.Item height="72px" />
        <Loader.Item height="320px" />
      </Loader>
    );

  // Somebody can be a member of the workspace without being employed through it.
  // With nobody to ask about, no request is made at all — so without this the
  // screen would fall through to its own defaults and state four confident
  // figures about a month it never fetched.
  if (!subjectId && !isManager)
    return (
      <div className="w-full">
        <EmptyStateCompact
          title={t("hr.my_time.no_record")}
          description={t("hr.my_time.no_record_detail")}
          assetKey="unknown"
          assetClassName="size-20"
          rootClassName="py-16"
        />
      </div>
    );

  // Only when there is nothing good to show — a failed revalidation must not
  // wipe a table somebody is reading.
  if ((error || meError) && (notAllowed || !data))
    return (
      <div className="w-full">
        <EmptyStateCompact
          title={notAllowed ? t("hr.team_time.not_permitted") : t("hr.shared.load_failed")}
          description={
            notAllowed
              ? t("hr.team_time.not_permitted_detail", { page: t("hr.my_time.title") })
              : t("hr.shared.load_failed_detail")
          }
          assetKey={notAllowed ? "members" : "unknown"}
          assetClassName="size-20"
          rootClassName="py-16"
          actions={
            notAllowed ? [] : [{ label: t("hr.shared.retry"), variant: "secondary", onClick: () => void mutate() }]
          }
        />
      </div>
    );

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <HrPeriodStepper
          label={monthLabel}
          onPrevious={() => setMonth(previousMonth(year, month))}
          onNext={() => setMonth(nextMonth(year, month))}
        />

        <div className="flex flex-wrap items-center gap-3">
          {isManager ? (
            <select
              value={personId}
              onChange={(event) => setPersonId(event.target.value)}
              aria-label={t("hr.detail.whose")}
              className="rounded-md border border-subtle bg-layer-1 px-3 py-1.5 text-13 text-secondary"
            >
              <option value="">{t("hr.detail.mine")}</option>
              {(people ?? []).map((person) => (
                <option key={person.id} value={person.id}>
                  {person.member_display_name || person.member_email}
                </option>
              ))}
            </select>
          ) : null}

          <select
            value={grouping}
            onChange={(event) => setGrouping(event.target.value as THrWorklogGrouping)}
            aria-label={t("hr.detail.group_by")}
            className="rounded-md border border-subtle bg-layer-1 px-3 py-1.5 text-13 text-secondary"
          >
            {GROUPINGS.map((value) => (
              <option key={value} value={value}>
                {t(`hr.detail.grouping.${value}`)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <HrFigure label={t("hr.detail.on_work_items")} value={formatMinutes(data?.work_item_minutes ?? 0)} />
        <HrFigure label={t("hr.detail.other_hours")} value={formatMinutes(data?.other_minutes ?? 0)} />
        <HrFigure
          label={t("hr.detail.entries")}
          value={String((data?.groups ?? []).reduce((total, row) => total + row.entries, 0))}
        />
        <HrFigure
          label={t("hr.detail.month_state")}
          value={data?.is_settled ? t("hr.detail.frozen") : t("hr.detail.live")}
          hint={data?.is_settled ? t("hr.detail.frozen_hint") : t("hr.detail.live_hint")}
        />
      </div>

      {data && data.running > 0 ? (
        <p className="inline-flex items-center gap-1.5 text-13 text-tertiary">
          <Timer className="size-3.5" />
          {t("hr.detail.running_note", { count: data.running })}
        </p>
      ) : null}

      {data && data.missing > 0 ? (
        <p className="inline-flex items-center gap-1.5 text-13 text-warning-primary">
          <AlertTriangle className="size-3.5" />
          {t("hr.detail.missing_note", { count: data.missing })}
        </p>
      ) : null}

      {(data?.groups ?? []).length === 0 ? (
        <div className="rounded-md border border-subtle bg-layer-1 px-4 py-6 text-13 text-tertiary">
          {t("hr.detail.nothing_logged")}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-subtle">
          <table className="w-full min-w-[52rem] text-13">
            <thead className="border-b border-subtle text-13 text-placeholder">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">{t("hr.detail.column_what")}</th>
                <th className="px-4 py-2.5 text-left font-medium">{t("hr.detail.column_when")}</th>
                <th className="px-4 py-2.5 text-left font-medium">{t("hr.detail.column_note")}</th>
                <th className="px-4 py-2.5 text-right font-medium">{t("hr.detail.column_long")}</th>
              </tr>
            </thead>
            <tbody>
              {(data?.groups ?? []).map((row) => {
                // Days open by default because that is the shape people read a
                // month in; the other groupings are a list to scan first.
                // Keyed by what is being looked at as well as by the group.
                // A day's key is its date, which is the same string for every
                // person and every month, so collapsing one person's Monday
                // used to collapse everybody's.
                const seat = `${subjectId}_${year}_${month}_${grouping}_${row.key}`;
                const isOpen = opened[seat] ?? grouping === "day";
                return (
                  <GroupRows
                    key={row.key}
                    group={row}
                    label={groupLabel(row)}
                    isOpen={isOpen}
                    onToggle={() => setOpened((current) => ({ ...current, [seat]: !isOpen }))}
                    locale={currentLocale}
                    t={t}
                    showDay={grouping !== "day"}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {(data?.other ?? []).length > 0 ? (
        <section className="flex flex-col gap-3">
          <h3 className="text-16 font-medium text-primary">{t("hr.detail.other_title")}</h3>
          <p className="text-13 text-tertiary">{t("hr.detail.other_subtitle")}</p>
          <div className="overflow-x-auto rounded-md border border-subtle">
            <table className="w-full min-w-[36rem] text-13">
              <thead className="border-b border-subtle text-13 text-placeholder">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium">{t("hr.detail.column_when")}</th>
                  <th className="px-4 py-2.5 text-left font-medium">{t("hr.detail.column_what")}</th>
                  <th className="px-4 py-2.5 text-left font-medium">{t("hr.detail.column_note")}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t("hr.detail.column_long")}</th>
                </tr>
              </thead>
              <tbody>
                {(data?.other ?? []).map((row) => (
                  <tr key={row.id} className="border-t border-subtle hover:bg-layer-1/60">
                    <td className="px-4 py-2 text-tertiary">{formatDayLabel(row.day, currentLocale)}</td>
                    <td className="px-4 py-2 text-primary">
                      {t(`hr.entries.category.${CATEGORY_KEY[row.category] ?? "admin"}`)}
                    </td>
                    <td className="px-4 py-2 text-tertiary">{row.note}</td>
                    <td className="px-4 py-2 text-right text-primary tabular-nums">{formatMinutes(row.minutes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <p className="text-13 text-tertiary">
        {data && !data.totals_reconcile ? `${t("hr.detail.rounding_note")} ` : ""}
        {t("hr.detail.footnote")}
      </p>
    </div>
  );
});

type TGroupProps = {
  group: THrWorklogGroup;
  label: string;
  isOpen: boolean;
  onToggle: () => void;
  locale?: string;
  t: (key: string, values?: Record<string, unknown>) => string;
  /** False when the group header already names the day these rows fall on. */
  showDay: boolean;
};

/** One group's header row, and its entries when it is open. */
const GroupRows = ({ group, label, isOpen, onToggle, locale, t, showDay }: TGroupProps) => (
  <>
    <tr className="border-t border-subtle bg-layer-1/40">
      <td colSpan={3} className="px-4 py-2">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isOpen}
          className="inline-flex items-center gap-1.5 rounded-md text-13 font-medium text-primary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
        >
          {isOpen ? (
            <ChevronDown className="size-3.5 text-tertiary" />
          ) : (
            <ChevronRight className="size-3.5 text-tertiary" />
          )}
          {label}
          <span className="font-normal text-13 text-tertiary">
            {t("hr.detail.entry_count", { count: group.entries })}
          </span>
        </button>
      </td>
      <td className="px-4 py-2 text-right font-medium text-primary tabular-nums">{formatMinutes(group.minutes)}</td>
    </tr>
    {isOpen
      ? group.rows.map((row) => <EntryRow key={row.id} row={row} locale={locale} t={t} showDay={showDay} />)
      : null}
  </>
);

/** One logged entry. */
const EntryRow = ({
  row,
  locale,
  t,
  showDay,
}: {
  row: THrWorklogRow;
  locale?: string;
  t: (key: string, values?: Record<string, unknown>) => string;
  showDay: boolean;
}) => {
  const duration = useRowDuration();
  const key =
    row.project_identifier && row.issue_sequence_id ? `${row.project_identifier}-${row.issue_sequence_id}` : "";
  return (
    <tr className={cn("border-t border-subtle hover:bg-layer-1/60", row.gone && "text-tertiary line-through")}>
      <td className="px-4 py-2">
        <div className="flex items-center gap-2">
          {key ? <span className="text-13 tracking-wide text-tertiary tabular-nums">{key}</span> : null}
          <span className="text-primary">{row.issue_name || t("hr.detail.unnamed")}</span>
          {row.is_running ? (
            <Tooltip tooltipContent={t("hr.detail.still_running")} position="top">
              <Timer className="size-3.5 text-warning-primary" aria-label={t("hr.detail.still_running")} />
            </Tooltip>
          ) : null}
          {row.gone ? (
            <Tooltip tooltipContent={t("hr.detail.gone")} position="top">
              <AlertTriangle className="size-3.5 text-warning-primary" aria-label={t("hr.detail.gone")} />
            </Tooltip>
          ) : null}
        </div>
        <div className="text-13 text-tertiary">{row.project_name}</div>
      </td>
      <td className="px-4 py-2 text-tertiary">
        {showDay ? formatDayLabel(row.day, locale) : null}
        {row.entered_by_hand ? <span className={showDay ? "ml-2" : undefined}>{t("hr.detail.by_hand")}</span> : null}
        {row.auto_stopped ? (
          <Tooltip tooltipContent={t("hr.detail.auto_stopped_hint")} position="top">
            <span className="ml-2 text-warning-primary">{t("hr.detail.auto_stopped")}</span>
          </Tooltip>
        ) : null}
      </td>
      <td className="px-4 py-2 text-tertiary">{row.note}</td>
      <td className="px-4 py-2 text-right text-primary tabular-nums">{duration(row.seconds)}</td>
    </tr>
  );
};
