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
  EHrPeriodState,
  EHrTimeCategory,
  HrService,
  type THrEmploymentProfile,
  type THrWorklogDetail,
  type THrWorklogGroup,
  type THrWorklogGrouping,
  type THrWorklogOtherRow,
  type THrWorklogRow,
} from "@/services/hr.service";
// local imports
import { HrFigure } from "./figure";
import { HrPeriodStepper } from "./period-stepper";
import {
  formatDayLabel,
  formatDayWithYear,
  formatMinutes,
  formatMonthLabel,
  nextMonth,
  periodStateKey,
  previousMonth,
} from "./utils";

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
 * Who is reading, and whose months they are allowed to open.
 *
 * A manager can look at anybody, so the list of people is worth fetching only
 * for one; everybody else only ever sees themselves.
 */
const useHrViewer = (personId: string) => {
  const { data: me, isLoading, error } = useSWR("HR_ME_ROLE", () => hrService.me());
  const isManager = Boolean(me?.is_hr_manager);
  const { data: people } = useSWR(isManager ? "HR_EMPLOYEES" : null, () => hrService.employees());

  return {
    isManager,
    people: people ?? [],
    // Whoever is being looked at: the person picked, or the reader themselves.
    subjectId: personId || me?.profile?.id || "",
    isLoading,
    error,
  };
};

/**
 * One person's month, once it is settled who that person is.
 *
 * Whether the screen is still waiting, and whether it has been left with
 * nothing, are both decided here rather than in the layout, because both turn
 * on the same thing: a month already on the table outranks a request that is
 * still in the air or has just come back empty-handed.
 */
const useWorklogDetail = (personId: string, year: number, month: number, grouping: THrWorklogGrouping) => {
  const viewer = useHrViewer(personId);
  const { subjectId } = viewer;

  const question = subjectId ? `HR_WORKLOG_DETAIL_${subjectId}_${year}_${month}_${grouping}` : null;

  const { data, isLoading, error, mutate } = useSWR(
    question,
    // Each month is kept alongside the question it answers, because the answer
    // itself cannot say whose hours it is.
    async () => ({ question, detail: await hrService.worklogDetail(subjectId, year, month, grouping) }),
    // The month, the person and the grouping are all in the key, so changing any
    // of them would otherwise empty the table and unmount the very control that
    // was just used — taking the keyboard focus, or the button under the cursor,
    // with it.
    { keepPreviousData: true }
  );

  const refusal = (error ?? viewer.error) as { status?: number } | undefined;
  const notAllowed = refusal?.status === 403;
  const isAnswer = data?.question === question;

  return {
    isManager: viewer.isManager,
    people: viewer.people,
    subjectId,
    detail: data?.detail ?? null,
    notAllowed,
    isLoading: (isLoading || viewer.isLoading) && !data,
    // Failed only when there is nothing good to show — a failed revalidation of
    // the month on screen must not wipe a table somebody is reading. A month
    // that was asked for and never arrived is a different matter: leaving the
    // one before it under the new month's label, or under somebody else's name,
    // would have it read as an answer it is not.
    hasFailed: Boolean(error || viewer.error) && (notAllowed || !isAnswer),
    retry: () => void mutate(),
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
 *
 * What is on screen is a handful of separate things — the controls that choose
 * what to show, the figures that summarise it, and the rows themselves — so
 * each of them is its own component. Only this one holds what was chosen, and
 * fetching what was chosen belongs to the hook above.
 */
export const HrWorklogDetailRoot = observer(function HrWorklogDetailRoot() {
  const { currentLocale } = useTranslation();
  const now = new Date();
  const [[year, month], setMonth] = useState<[number, number]>([now.getFullYear(), now.getMonth() + 1]);
  const [grouping, setGrouping] = useState<THrWorklogGrouping>("day");
  const [personId, setPersonId] = useState("");
  const [opened, setOpened] = useState<Record<string, boolean>>({});

  const { isManager, people, subjectId, detail, notAllowed, isLoading, hasFailed, retry } = useWorklogDetail(
    personId,
    year,
    month,
    grouping
  );

  const monthLabel = formatMonthLabel(`${year}-${String(month).padStart(2, "0")}-01`, currentLocale);

  if (isLoading)
    return (
      <Loader className="flex w-full flex-col gap-3">
        <Loader.Item height="72px" />
        <Loader.Item height="320px" />
      </Loader>
    );

  // Somebody can be a member of the workspace without being employed through it.
  // For them there is nothing here at all and nothing to choose from, where a
  // manager with no hours of their own has everybody else's to look at.
  if (!subjectId && !isManager) return <NoEmploymentRecord />;

  if (hasFailed) return <DetailUnavailable notAllowed={notAllowed} onRetry={retry} />;

  return (
    <div className="flex w-full flex-col gap-7">
      <DetailControls
        monthLabel={monthLabel}
        onPreviousMonth={() => setMonth(previousMonth(year, month))}
        onNextMonth={() => setMonth(nextMonth(year, month))}
        isManager={isManager}
        people={people}
        personId={personId}
        onPersonChange={setPersonId}
        grouping={grouping}
        onGroupingChange={setGrouping}
      />

      {subjectId ? (
        <>
          <DetailSummary detail={detail} />

          <DetailTable
            detail={detail}
            grouping={grouping}
            scope={`${subjectId}_${year}_${month}_${grouping}`}
            opened={opened}
            onToggle={(seat, nextOpen) => setOpened((current) => ({ ...current, [seat]: nextOpen }))}
            locale={currentLocale}
          />

          <OtherHours detail={detail} locale={currentLocale} />

          <DetailFootnote detail={detail} />
        </>
      ) : (
        <NobodyChosen />
      )}
    </div>
  );
});

/** Whose hours, which month, and how they are gathered. */
const DetailControls = ({
  monthLabel,
  onPreviousMonth,
  onNextMonth,
  isManager,
  people,
  personId,
  onPersonChange,
  grouping,
  onGroupingChange,
}: {
  monthLabel: string;
  onPreviousMonth: () => void;
  onNextMonth: () => void;
  isManager: boolean;
  people: THrEmploymentProfile[];
  personId: string;
  onPersonChange: (value: string) => void;
  grouping: THrWorklogGrouping;
  onGroupingChange: (value: THrWorklogGrouping) => void;
}) => {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <HrPeriodStepper label={monthLabel} onPrevious={onPreviousMonth} onNext={onNextMonth} />

      <div className="flex flex-wrap items-center gap-3">
        {isManager ? (
          <select
            value={personId}
            onChange={(event) => onPersonChange(event.target.value)}
            aria-label={t("hr.detail.whose")}
            className="rounded-md border border-subtle bg-layer-1 px-3 py-1.5 text-13 text-secondary"
          >
            <option value="">{t("hr.detail.mine")}</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.member_display_name || person.member_email}
              </option>
            ))}
          </select>
        ) : null}

        <select
          value={grouping}
          onChange={(event) => onGroupingChange(event.target.value as THrWorklogGrouping)}
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
  );
};

/**
 * What the month comes to, and the two things those figures cannot say alone:
 * a timer still running counts nothing yet, and an entry the month counted may
 * no longer be there to show.
 */
const DetailSummary = ({ detail }: { detail: THrWorklogDetail | null }) => {
  const { t } = useTranslation();

  return (
    <>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <HrFigure label={t("hr.detail.on_work_items")} value={formatMinutes(detail?.work_item_minutes ?? 0)} />
        <HrFigure label={t("hr.detail.other_hours")} value={formatMinutes(detail?.other_minutes ?? 0)} />
        <HrFigure
          label={t("hr.detail.entries")}
          value={String((detail?.groups ?? []).reduce((total, row) => total + row.entries, 0))}
        />
        {/*
         * The month's own word, not a word of this screen's invention: a month
         * that has merely been handed in is not the same thing as one payroll
         * has closed, and somebody who spots a mistake the next day needs to
         * know which of the two they are looking at. A month nobody has ever
         * opened has not been handed in, so that is what it says. The hint
         * still answers the other question — whether these hours can change.
         */}
        <HrFigure
          label={t("hr.detail.month_state")}
          value={t(periodStateKey(detail?.period_state ?? EHrPeriodState.OPEN))}
          hint={detail?.is_settled ? t("hr.detail.frozen_hint") : t("hr.detail.live_hint")}
        />
      </div>

      {detail && detail.running > 0 ? (
        <p className="inline-flex items-center gap-1.5 text-13 text-tertiary">
          <Timer className="size-3.5" />
          {t("hr.detail.running_note", { count: detail.running })}
        </p>
      ) : null}

      {detail && detail.missing > 0 ? (
        <p className="inline-flex items-center gap-1.5 text-13 text-warning-primary">
          <AlertTriangle className="size-3.5" />
          {t("hr.detail.missing_note", { count: detail.missing })}
        </p>
      ) : null}
    </>
  );
};

/** The month's work-item hours, gathered the way the reader asked for them. */
const DetailTable = ({
  detail,
  grouping,
  scope,
  opened,
  onToggle,
  locale,
}: {
  detail: THrWorklogDetail | null;
  grouping: THrWorklogGrouping;
  /**
   * Which person, month and grouping these rows belong to. A day's key is only
   * its date — the same string for every person and every month — so without
   * this, collapsing one person's Monday collapsed everybody's.
   */
  scope: string;
  opened: Record<string, boolean>;
  onToggle: (seat: string, nextOpen: boolean) => void;
  locale?: string;
}) => {
  const { t } = useTranslation();
  const groups = detail?.groups ?? [];

  const groupLabel = (row: THrWorklogGroup) => {
    if (grouping === "day") return formatDayLabel(row.first_day, locale);
    if (grouping === "week") return t("hr.detail.week_of", { date: formatDayWithYear(row.first_day, locale) });
    return row.label || t("hr.detail.unnamed");
  };

  if (groups.length === 0)
    return (
      <div className="rounded-md border border-subtle bg-layer-1 px-4 py-6 text-13 text-tertiary">
        {t("hr.detail.nothing_logged")}
      </div>
    );

  return (
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
          {groups.map((row) => {
            // Days open by default, because that is the shape people read a
            // month in; the other groupings are a list to scan first.
            const seat = `${scope}_${row.key}`;
            const isOpen = opened[seat] ?? grouping === "day";
            return (
              <GroupRows
                key={row.key}
                group={row}
                label={groupLabel(row)}
                isOpen={isOpen}
                onToggle={() => onToggle(seat, !isOpen)}
                locale={locale}
                showDay={grouping !== "day"}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

/**
 * Hours with no work item behind them — the other half of the day.
 *
 * Its own table rather than rows mixed into the one above: these have no work
 * item at all and their project is optional, so several columns would be
 * structurally empty, and presenting them as work-item time would tell the
 * story wrong.
 */
const OtherHours = ({ detail, locale }: { detail: THrWorklogDetail | null; locale?: string }) => {
  const { t } = useTranslation();
  const rows: THrWorklogOtherRow[] = detail?.other ?? [];
  if (rows.length === 0) return null;

  return (
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
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-subtle hover:bg-layer-1/60">
                <td className="px-4 py-2 text-tertiary">{formatDayLabel(row.day, locale)}</td>
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
  );
};

/** One group's header row, and its entries when it is open. */
const GroupRows = ({
  group,
  label,
  isOpen,
  onToggle,
  locale,
  showDay,
}: {
  group: THrWorklogGroup;
  label: string;
  isOpen: boolean;
  onToggle: () => void;
  locale?: string;
  /** False when the group header already names the day these rows fall on. */
  showDay: boolean;
}) => {
  const { t } = useTranslation();

  return (
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
      {isOpen ? group.rows.map((row) => <EntryRow key={row.id} row={row} locale={locale} showDay={showDay} />) : null}
    </>
  );
};

/** One logged entry. */
const EntryRow = ({ row, locale, showDay }: { row: THrWorklogRow; locale?: string; showDay: boolean }) => {
  const { t } = useTranslation();
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

/** The small print, plus the warning the months that do not add up have earned. */
const DetailFootnote = ({ detail }: { detail: THrWorklogDetail | null }) => {
  const { t } = useTranslation();

  return (
    <p className="text-13 text-tertiary">
      {detail && !detail.totals_reconcile ? `${t("hr.detail.rounding_note")} ` : ""}
      {t("hr.detail.footnote")}
    </p>
  );
};

/**
 * Somebody who looks after the team but has no hours of their own — typically
 * whoever administers the installation.
 *
 * There is nobody to ask about until they choose, so nothing was fetched, and a
 * screen that filled the gap with its own defaults would state four confident
 * figures — no hours, no entries, a month still open — about a month it never
 * asked for. The reasonable conclusion from that is that hours have been lost.
 */
const NobodyChosen = () => {
  const { t } = useTranslation();

  return (
    <div className="rounded-md border border-subtle bg-layer-1 px-4 py-6 text-13 text-tertiary">
      {t("hr.people.pick_somebody_first")}
    </div>
  );
};

/** Somebody the workspace knows, but the employer does not. */
const NoEmploymentRecord = () => {
  const { t } = useTranslation();

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
};

/**
 * Why there is no month on screen. Either it was never this reader's to see, in
 * which case asking again would only be refused again, or it simply did not
 * arrive — and that one is worth another try.
 */
const DetailUnavailable = ({ notAllowed, onRetry }: { notAllowed: boolean; onRetry: () => void }) => {
  const { t } = useTranslation();

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
        actions={notAllowed ? [] : [{ label: t("hr.shared.retry"), variant: "secondary", onClick: onRetry }]}
      />
    </div>
  );
};
