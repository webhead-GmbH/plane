/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Link } from "react-router";
import { CalendarClock, ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
// services
import { HrService, type THrHoliday } from "@/services/hr.service";
// local imports
import { formatDayWithYear, refusalMessage } from "./utils";

const hrService = new HrService();

/** A whole day, or the half that 24 and 31 December usually are. */
const WHOLE_DAY = "1.00";
const HALF_DAY = "0.50";

const isHalf = (fraction: string) => Number(fraction) < 1;

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
export const HrHolidaysRoot = observer(function HrHolidaysRoot({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [calendarId, setCalendarId] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const [date, setDate] = useState("");
  const [name, setName] = useState("");
  const [half, setHalf] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const {
    data: calendars,
    isLoading: loadingCalendars,
    error,
  } = useSWR("HR_HOLIDAY_CALENDARS", () => hrService.holidayCalendars());

  // Whichever calendar is marked the default is the one to open on, since it is
  // the one nearly everybody is on.
  useEffect(() => {
    if (calendarId || !calendars?.length) return;
    setCalendarId((calendars.find((row) => row.is_default) ?? calendars[0]).id);
  }, [calendars, calendarId]);

  const {
    data: holidays,
    isLoading: loadingHolidays,
    mutate,
  } = useSWR(calendarId ? `HR_HOLIDAYS_${calendarId}_${year}` : null, () =>
    calendarId ? hrService.holidays(calendarId, year) : null
  );

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.holidays.toasts.refused"),
      message: refusalMessage(failure) ?? t("hr.holidays.toasts.try_again"),
    });

  const handleAdd = async () => {
    if (!calendarId) return;
    if (!date || !name.trim()) {
      setProblem(t("hr.holidays.errors.date_and_name"));
      return;
    }

    setIsBusy(true);
    try {
      await hrService.createHoliday({
        calendar: calendarId,
        date,
        name_de: name.trim(),
        day_fraction: half ? HALF_DAY : WHOLE_DAY,
        // Anything added by hand is a day the company grants. A statutory holiday
        // comes from the seeding, and calling a granted day statutory would claim
        // a pay entitlement that does not exist.
        is_statutory: false,
      });
      setDate("");
      setName("");
      setHalf(false);
      setProblem(null);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.holidays.toasts.added") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleToggleHalf = async (holiday: THrHoliday) => {
    setIsBusy(true);
    try {
      await hrService.updateHoliday(holiday.id, {
        day_fraction: isHalf(holiday.day_fraction) ? WHOLE_DAY : HALF_DAY,
      });
      await mutate();
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleRemove = async (holiday: THrHoliday) => {
    setIsBusy(true);
    try {
      await hrService.deleteHoliday(holiday.id);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.holidays.toasts.removed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  if (loadingCalendars)
    return (
      <Loader className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-6 py-6">
        <Loader.Item height="48px" />
        <Loader.Item height="280px" />
      </Loader>
    );

  if (error)
    return (
      <div className="mx-auto w-full max-w-5xl px-6 py-6">
        <div className="border-custom-border-200 bg-custom-background-90 rounded-md border px-4 py-6">
          <p className="text-custom-text-200 text-sm font-medium">{t("hr.team_time.not_permitted")}</p>
          <p className="text-custom-text-300 text-sm mt-1">{t("hr.holidays.not_permitted_detail")}</p>
        </div>
      </div>
    );

  const rows = holidays ?? [];

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-6 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-custom-text-100 text-lg font-semibold">{t("hr.holidays.title")}</h1>
          <p className="text-custom-text-300 text-sm">{t("hr.holidays.subtitle")}</p>
        </div>
        <Link to={`/${workspaceSlug}/team-time`}>
          <Button variant="secondary" size="sm" prependIcon={<CalendarClock className="size-4" />}>
            {t("hr.holidays.back_to_month")}
          </Button>
        </Link>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          value={calendarId ?? ""}
          onChange={(event) => setCalendarId(event.target.value)}
          aria-label={t("hr.holidays.calendar")}
          className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 text-sm rounded border px-2 py-1"
        >
          {(calendars ?? []).map((row) => (
            <option key={row.id} value={row.id}>
              {row.name} ({row.country_code})
            </option>
          ))}
        </select>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setYear(year - 1)}
            aria-label={t("hr.holidays.previous_year")}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-custom-text-100 text-sm min-w-[4rem] text-center font-medium">{year}</span>
          <Button variant="ghost" size="sm" onClick={() => setYear(year + 1)} aria-label={t("hr.holidays.next_year")}>
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>

      {loadingHolidays ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="200px" />
        </Loader>
      ) : rows.length === 0 ? (
        <div className="border-custom-border-200 bg-custom-background-90 text-custom-text-300 text-sm rounded-md border px-4 py-8 text-center">
          {t("hr.holidays.none_this_year")}
        </div>
      ) : (
        <div className="border-custom-border-200 overflow-x-auto rounded-md border">
          <table className="text-sm w-full min-w-[36rem]">
            <thead className="bg-custom-background-90 text-custom-text-400 text-xs tracking-wide uppercase">
              <tr>
                <th className="px-4 py-2 text-left font-medium">{t("hr.holidays.column_date")}</th>
                <th className="px-4 py-2 text-left font-medium">{t("hr.holidays.column_name")}</th>
                <th className="px-4 py-2 text-left font-medium">{t("hr.holidays.column_kind")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("hr.holidays.column_action")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((holiday) => (
                <tr key={holiday.id} className="border-custom-border-200 hover:bg-custom-background-90/60 border-t">
                  <td className="text-custom-text-200 px-4 py-2 whitespace-nowrap">
                    {formatDayWithYear(holiday.date)}
                  </td>
                  <td className="text-custom-text-100 px-4 py-2">{holiday.name_de}</td>
                  <td className="px-4 py-2">
                    <span className="text-custom-text-300 text-xs">
                      {holiday.is_statutory ? t("hr.holidays.statutory") : t("hr.holidays.granted")}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center justify-end gap-2">
                      <Button variant="link" size="sm" loading={isBusy} onClick={() => void handleToggleHalf(holiday)}>
                        {isHalf(holiday.day_fraction) ? t("hr.holidays.make_whole") : t("hr.holidays.make_half")}
                      </Button>
                      {/* A statutory day is not the company's to remove. */}
                      {holiday.is_statutory ? null : (
                        <Button
                          variant="link"
                          size="sm"
                          loading={isBusy}
                          onClick={() => void handleRemove(holiday)}
                          aria-label={t("hr.holidays.remove")}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="border-custom-border-200 flex flex-col gap-3 rounded-md border p-3">
        <p className="text-custom-text-200 text-sm font-medium">{t("hr.holidays.add")}</p>

        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="text-custom-text-300 text-xs" htmlFor="hr-holiday-date">
              {t("hr.holidays.column_date")}
            </label>
            <input
              id="hr-holiday-date"
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 text-sm block rounded border px-2 py-1"
            />
          </div>

          <div className="min-w-[12rem] flex-1">
            <label className="text-custom-text-300 text-xs" htmlFor="hr-holiday-name">
              {t("hr.holidays.column_name")}
            </label>
            <input
              id="hr-holiday-name"
              type="text"
              value={name}
              placeholder={t("hr.holidays.name_placeholder")}
              onChange={(event) => setName(event.target.value)}
              className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 text-sm block w-full rounded border px-2 py-1"
            />
          </div>

          <label className="text-custom-text-300 text-sm flex items-center gap-2" htmlFor="hr-holiday-half">
            <input
              id="hr-holiday-half"
              type="checkbox"
              checked={half}
              onChange={(event) => setHalf(event.target.checked)}
            />
            {t("hr.holidays.only_half")}
          </label>

          <Button
            variant="primary"
            size="sm"
            loading={isBusy}
            prependIcon={<Plus className="size-4" />}
            onClick={() => void handleAdd()}
          >
            {t("hr.holidays.add_button")}
          </Button>
        </div>

        {problem && <p className="text-xs text-red-500">{problem}</p>}
      </div>
    </div>
  );
});
