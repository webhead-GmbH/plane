/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { ChevronLeft, ChevronRight, Circle, Contrast, Plus, Trash2 } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { AlertModalCore, Loader } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import { HrService, type THrHoliday, type THrHolidayCalendar } from "@/services/hr.service";
// local imports
import { HrRowAction } from "./row-action";
import { formatDayWithYear, localName, refusalMessage } from "./utils";

const hrService = new HrService();

/** A whole day, or the half that 24 and 31 December usually are. */
const WHOLE_DAY = "1.00";
const HALF_DAY = "0.50";

const isHalf = (fraction: string) => Number(fraction) < 1;

/** The length a day takes on when somebody says it was the other kind. */
const otherLength = (fraction: string) => (isHalf(fraction) ? WHOLE_DAY : HALF_DAY);

type TTranslate = (key: string, values?: Record<string, unknown>) => string;

/** The server's own words where it named a reason, and an apology where it did not. */
const complainAbout = (failure: unknown, t: TTranslate, locale?: string) =>
  setToast({
    type: TOAST_TYPE.ERROR,
    title: t("hr.holidays.toasts.refused"),
    message: refusalMessage(failure, t, locale) ?? t("hr.holidays.toasts.try_again"),
  });

/** The reader is not on the HR team, which is a different thing from a broken request. */
const isForbidden = (failure: unknown) => (failure as { status?: number } | undefined)?.status === 403;

/**
 * Only when there is nothing to show: a revalidation that failed while the
 * screen already holds good data must not replace it with an error.
 */
const nothingToShow = (failure: unknown, calendars: THrHolidayCalendar[] | undefined) =>
  Boolean(failure) && (isForbidden(failure) || !calendars);

const defaultCalendar = (calendars: THrHolidayCalendar[]) => calendars.find((row) => row.is_default) ?? calendars[0];

/**
 * The days nobody works, and which of them are only half.
 *
 * Austria's statutory holidays are seeded, and they are federal — identical in
 * every Bundesland — so there is nothing to choose between regions. What is left
 * for somebody to say is the part no statute settles: 24 and 31 December are half
 * days by agreement rather than by law, a company may grant a day of its own, and
 * anyone habitually working elsewhere needs a calendar that is not Austria's.
 *
 * A holiday reduces the target for the day rather than adding to what was worked,
 * which is why the fraction matters here and not anywhere else: half a day off is
 * half a day of target, and getting it wrong moves somebody's balance by four
 * hours without anything on the screen looking unusual.
 */
export const HrHolidaysRoot = observer(function HrHolidaysRoot() {
  const { t, currentLocale } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [calendarId, setCalendarId] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [removing, setRemoving] = useState<THrHoliday | null>(null);

  // The day somebody is part-way through typing lives up here rather than down in
  // the form. A refused reload takes the whole screen away for as long as it
  // lasts, and the half-written day should be waiting again afterwards instead of
  // having to be remembered and typed a second time.
  const [date, setDate] = useState("");
  const [name, setName] = useState("");
  const [half, setHalf] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const {
    data: calendars,
    isLoading: loadingCalendars,
    error,
    mutate: retryCalendars,
  } = useSWR("HR_HOLIDAY_CALENDARS", () => hrService.holidayCalendars());

  // Whichever calendar is marked the default is the one to open on, since it is
  // the one nearly everybody is on.
  useEffect(() => {
    if (calendarId || !calendars?.length) return;
    setCalendarId(defaultCalendar(calendars).id);
  }, [calendars, calendarId]);

  const {
    data: holidays,
    isLoading: loadingHolidays,
    mutate,
  } = useSWR(calendarId ? `HR_HOLIDAYS_${calendarId}_${year}` : null, () =>
    calendarId ? hrService.holidays(calendarId, year) : null
  );

  const handleAdd = async () => {
    if (!calendarId) return;
    if (!date || !name.trim()) {
      setProblem(t("hr.holidays.errors.date_and_name"));
      return;
    }
    const clash = (holidays ?? []).find((row) => row.date === date);
    if (clash) {
      setProblem(t("hr.holidays.errors.already_there", { day: localName(clash, currentLocale) }));
      return;
    }

    setIsBusy(true);
    try {
      await hrService.createHoliday({
        calendar: calendarId,
        date,
        // The same name in both. A day the company grants has one name — the
        // one the person adding it typed — and writing it only into the German
        // field would leave it unreadable on an English screen, which is the
        // problem this replaces rather than one to add more of.
        name_de: name.trim(),
        name_en: name.trim(),
        day_fraction: half ? HALF_DAY : WHOLE_DAY,
        // Anything added by hand is a day the company grants. A statutory holiday
        // comes from the seeding, and calling a granted day statutory would claim
        // a pay entitlement that does not exist.
        is_statutory: false,
      });
      // Read the year off the date before it is cleared: a day added into a
      // different year would otherwise be written correctly and then be
      // invisible, because the table is still showing the year it was added from.
      const landedIn = Number(date.slice(0, 4));
      setDate("");
      setName("");
      setHalf(false);
      setProblem(null);
      if (!Number.isNaN(landedIn) && landedIn !== year) setYear(landedIn);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.holidays.toasts.added") });
    } catch (failure) {
      complainAbout(failure, t, currentLocale);
    } finally {
      setIsBusy(false);
    }
  };

  const handleToggleHalf = async (holiday: THrHoliday) => {
    setIsBusy(true);
    try {
      await hrService.updateHoliday(holiday.id, {
        day_fraction: otherLength(holiday.day_fraction),
      });
      await mutate();
    } catch (failure) {
      complainAbout(failure, t, currentLocale);
    } finally {
      setIsBusy(false);
    }
  };

  const handleRemove = async () => {
    if (!removing) return;
    setIsBusy(true);
    try {
      await hrService.deleteHoliday(removing.id);
      await mutate();
      setRemoving(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.holidays.toasts.removed") });
    } catch (failure) {
      complainAbout(failure, t, currentLocale);
    } finally {
      setIsBusy(false);
    }
  };

  if (loadingCalendars)
    return (
      <Loader className="flex w-full flex-col gap-7">
        <Loader.Item height="48px" />
        <Loader.Item height="280px" />
      </Loader>
    );

  if (nothingToShow(error, calendars))
    return <HolidaysUnavailable notAllowed={isForbidden(error)} onRetry={() => void retryCalendars()} />;

  const rows = holidays ?? [];

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-13 text-tertiary">{t("hr.holidays.subtitle")}</p>
      </div>

      <HolidayScope
        calendars={calendars}
        calendarId={calendarId}
        onCalendar={setCalendarId}
        year={year}
        onYear={setYear}
      />

      <AddHolidayForm
        date={date}
        name={name}
        half={half}
        problem={problem}
        isBusy={isBusy}
        onDate={setDate}
        onName={setName}
        onHalf={setHalf}
        onAdd={() => void handleAdd()}
      />

      {/* A granted day is somebody's agreement with the team, and removing it
          silently lengthens their target for that day. */}

      {loadingHolidays ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="200px" />
        </Loader>
      ) : rows.length === 0 ? (
        <EmptyStateCompact
          title={t("hr.holidays.none_this_year")}
          assetKey="note"
          assetClassName="size-20"
          rootClassName="py-16"
        />
      ) : (
        <HolidayTable
          rows={rows}
          isBusy={isBusy}
          onToggleHalf={(holiday) => void handleToggleHalf(holiday)}
          onRemove={setRemoving}
        />
      )}

      <AlertModalCore
        isOpen={removing !== null}
        handleClose={() => setRemoving(null)}
        handleSubmit={() => void handleRemove()}
        isSubmitting={isBusy}
        variant="danger"
        title={t("hr.holidays.confirm_remove_title")}
        content={t("hr.holidays.confirm_remove_body", { day: localName(removing, currentLocale) })}
        primaryButtonText={{ default: t("hr.holidays.remove"), loading: t("hr.holidays.removing") }}
      />
    </div>
  );
});

type TUnavailableProps = {
  /** Refused rather than broken, which is worth saying differently. */
  notAllowed: boolean;
  onRetry: () => void;
};

const HolidaysUnavailable = ({ notAllowed, onRetry }: TUnavailableProps) => {
  const { t } = useTranslation();
  return (
    <div className="w-full">
      <EmptyStateCompact
        title={notAllowed ? t("hr.team_time.not_permitted") : t("hr.shared.load_failed")}
        description={notAllowed ? t("hr.holidays.not_permitted_detail") : t("hr.shared.load_failed_detail")}
        assetKey={notAllowed ? "members" : "unknown"}
        assetClassName="size-20"
        rootClassName="py-16"
        actions={notAllowed ? undefined : [{ label: t("hr.shared.retry"), variant: "secondary", onClick: onRetry }]}
      />
    </div>
  );
};

type TScopeProps = {
  calendars: THrHolidayCalendar[] | undefined;
  calendarId: string | null;
  onCalendar: (calendarId: string) => void;
  year: number;
  onYear: (year: number) => void;
};

/** Which calendar the days belong to, and which year of it is on screen. */
const HolidayScope = ({ calendars, calendarId, onCalendar, year, onYear }: TScopeProps) => {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-3">
      <select
        value={calendarId ?? ""}
        onChange={(event) => onCalendar(event.target.value)}
        aria-label={t("hr.holidays.calendar")}
        className="rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
      >
        {(calendars ?? []).map((row) => (
          <option key={row.id} value={row.id}>
            {row.name} ({row.country_code})
          </option>
        ))}
      </select>

      <div className="flex items-center gap-1">
        <Button variant="ghost" size="lg" onClick={() => onYear(year - 1)} aria-label={t("hr.holidays.previous_year")}>
          <ChevronLeft className="size-4" />
        </Button>
        <span className="min-w-[4rem] text-center text-13 font-medium text-primary">{year}</span>
        <Button variant="ghost" size="lg" onClick={() => onYear(year + 1)} aria-label={t("hr.holidays.next_year")}>
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
};

type TAddFormProps = {
  date: string;
  name: string;
  half: boolean;
  /** What is wrong with the day as it stands, in the words the reader is shown. */
  problem: string | null;
  isBusy: boolean;
  onDate: (date: string) => void;
  onName: (name: string) => void;
  onHalf: (half: boolean) => void;
  onAdd: () => void;
};

const AddHolidayForm = ({ date, name, half, problem, isBusy, onDate, onName, onHalf, onAdd }: TAddFormProps) => {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
      <p className="text-13 font-medium text-secondary">{t("hr.holidays.add")}</p>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="text-13 text-tertiary" htmlFor="hr-holiday-date">
            {t("hr.holidays.column_date")}
          </label>
          <input
            id="hr-holiday-date"
            type="date"
            value={date}
            onChange={(event) => onDate(event.target.value)}
            className="block rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
          />
        </div>

        <div className="min-w-[12rem] flex-1">
          <label className="text-13 text-tertiary" htmlFor="hr-holiday-name">
            {t("hr.holidays.column_name")}
          </label>
          <input
            id="hr-holiday-name"
            type="text"
            value={name}
            placeholder={t("hr.holidays.name_placeholder")}
            onChange={(event) => onName(event.target.value)}
            className="block w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
          />
        </div>

        <label className="flex items-center gap-2 text-13 text-tertiary" htmlFor="hr-holiday-half">
          <input
            id="hr-holiday-half"
            type="checkbox"
            checked={half}
            onChange={(event) => onHalf(event.target.checked)}
          />
          {t("hr.holidays.only_half")}
        </label>

        <Button variant="primary" size="lg" loading={isBusy} prependIcon={<Plus />} onClick={onAdd}>
          {t("hr.holidays.add_button")}
        </Button>
      </div>

      {problem && <p className="text-13 text-danger-primary">{problem}</p>}
    </div>
  );
};

type TTableProps = {
  rows: THrHoliday[];
  isBusy: boolean;
  onToggleHalf: (holiday: THrHoliday) => void;
  onRemove: (holiday: THrHoliday) => void;
};

const HolidayTable = ({ rows, isBusy, onToggleHalf, onRemove }: TTableProps) => {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto rounded-md border border-subtle">
      <table className="w-full min-w-[36rem] text-13">
        <thead className="border-b border-subtle text-13 text-placeholder">
          <tr>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.holidays.column_date")}</th>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.holidays.column_name")}</th>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.holidays.column_kind")}</th>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.holidays.column_length")}</th>
            <th className="px-4 py-2.5 text-right font-medium">{t("hr.holidays.column_action")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((holiday) => (
            <HolidayRow
              key={holiday.id}
              holiday={holiday}
              isBusy={isBusy}
              onToggleHalf={onToggleHalf}
              onRemove={onRemove}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

type TRowProps = {
  holiday: THrHoliday;
  isBusy: boolean;
  onToggleHalf: (holiday: THrHoliday) => void;
  onRemove: (holiday: THrHoliday) => void;
};

const HolidayRow = ({ holiday, isBusy, onToggleHalf, onRemove }: TRowProps) => {
  const { t, currentLocale } = useTranslation();
  const day = localName(holiday, currentLocale);
  return (
    <tr className="border-t border-subtle hover:bg-layer-1/60">
      <td className="px-4 py-2 whitespace-nowrap text-secondary">{formatDayWithYear(holiday.date, currentLocale)}</td>
      <td className="px-4 py-2 text-primary">{day}</td>
      <td className="px-4 py-2">
        <span className="text-13 text-tertiary">
          {holiday.is_statutory ? t("hr.holidays.statutory") : t("hr.holidays.granted")}
        </span>
      </td>
      {/* How long the day is, as a value. It used to be readable only
          by reading the action that would change it, so the column
          said what you could do rather than what was true — and the
          fraction is what moves somebody's balance. */}
      <td className="px-4 py-2">
        <span
          className={cn(
            "rounded-sm px-1.5 py-0.5 text-13 font-medium",
            isHalf(holiday.day_fraction) ? "bg-warning-subtle text-warning-primary" : "text-tertiary"
          )}
        >
          {isHalf(holiday.day_fraction) ? t("hr.holidays.half_day") : t("hr.holidays.whole_day")}
        </span>
      </td>
      <td className="px-4 py-2">
        <div className="flex items-center justify-end gap-0.5">
          <HolidayRowActions
            holiday={holiday}
            day={day}
            isBusy={isBusy}
            onToggleHalf={onToggleHalf}
            onRemove={onRemove}
          />
        </div>
      </td>
    </tr>
  );
};

type TRowActionsProps = TRowProps & {
  /** The day by the name the reader knows it by. */
  day: string;
};

/**
 * A statutory day is a whole day by law and is not the company's to shorten or to
 * remove — halving one here would quietly raise ten people's target for that day.
 * The half days that do exist by agreement, 24 and 31 December, are granted rather
 * than statutory and keep their toggle.
 */
const HolidayRowActions = ({ holiday, day, isBusy, onToggleHalf, onRemove }: TRowActionsProps) => {
  const { t } = useTranslation();
  if (holiday.is_statutory) return null;
  return (
    <>
      <HrRowAction
        icon={isHalf(holiday.day_fraction) ? <Circle className="size-4" /> : <Contrast className="size-4" />}
        label={isHalf(holiday.day_fraction) ? t("hr.holidays.make_whole") : t("hr.holidays.make_half")}
        subject={day}
        disabled={isBusy}
        onClick={() => onToggleHalf(holiday)}
      />
      <HrRowAction
        icon={<Trash2 className="size-4" />}
        label={t("hr.holidays.remove")}
        subject={day}
        danger
        disabled={isBusy}
        onClick={() => onRemove(holiday)}
      />
    </>
  );
};
