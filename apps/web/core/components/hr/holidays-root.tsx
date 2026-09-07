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
import { HrService, type THrHoliday } from "@/services/hr.service";
// local imports
import { HrRowAction } from "./row-action";
import { formatDayWithYear, localName, refusalMessage } from "./utils";

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
export const HrHolidaysRoot = observer(function HrHolidaysRoot() {
  const { t, currentLocale } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [calendarId, setCalendarId] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const [date, setDate] = useState("");
  const [name, setName] = useState("");
  const [half, setHalf] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [removing, setRemoving] = useState<THrHoliday | null>(null);

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
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.holidays.toasts.try_again"),
    });

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

  const handleRemove = async () => {
    if (!removing) return;
    setIsBusy(true);
    try {
      await hrService.deleteHoliday(removing.id);
      await mutate();
      setRemoving(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.holidays.toasts.removed") });
    } catch (failure) {
      complain(failure);
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

  const notAllowed = (error as { status?: number } | undefined)?.status === 403;
  const hasData = Boolean(calendars);

  // Only when there is nothing to show: a revalidation that failed while the
  // screen already holds good data must not replace it with an error.
  if (error && (notAllowed || !hasData))
    return (
      <div className="w-full">
        <EmptyStateCompact
          title={notAllowed ? t("hr.team_time.not_permitted") : t("hr.shared.load_failed")}
          description={notAllowed ? t("hr.holidays.not_permitted_detail") : t("hr.shared.load_failed_detail")}
          assetKey={notAllowed ? "members" : "unknown"}
          assetClassName="size-20"
          rootClassName="py-16"
          actions={
            notAllowed
              ? undefined
              : [{ label: t("hr.shared.retry"), variant: "secondary", onClick: () => void retryCalendars() }]
          }
        />
      </div>
    );

  const rows = holidays ?? [];

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-13 text-tertiary">{t("hr.holidays.subtitle")}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          value={calendarId ?? ""}
          onChange={(event) => setCalendarId(event.target.value)}
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
          <Button
            variant="ghost"
            size="lg"
            onClick={() => setYear(year - 1)}
            aria-label={t("hr.holidays.previous_year")}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="min-w-[4rem] text-center text-13 font-medium text-primary">{year}</span>
          <Button variant="ghost" size="lg" onClick={() => setYear(year + 1)} aria-label={t("hr.holidays.next_year")}>
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>

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
              onChange={(event) => setDate(event.target.value)}
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
              onChange={(event) => setName(event.target.value)}
              className="block w-full rounded border border-subtle bg-layer-1 px-2 py-1 text-13 text-primary"
            />
          </div>

          <label className="flex items-center gap-2 text-13 text-tertiary" htmlFor="hr-holiday-half">
            <input
              id="hr-holiday-half"
              type="checkbox"
              checked={half}
              onChange={(event) => setHalf(event.target.checked)}
            />
            {t("hr.holidays.only_half")}
          </label>

          <Button variant="primary" size="lg" loading={isBusy} prependIcon={<Plus />} onClick={() => void handleAdd()}>
            {t("hr.holidays.add_button")}
          </Button>
        </div>

        {problem && <p className="text-13 text-danger-primary">{problem}</p>}
      </div>

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
                <tr key={holiday.id} className="border-t border-subtle hover:bg-layer-1/60">
                  <td className="px-4 py-2 whitespace-nowrap text-secondary">
                    {formatDayWithYear(holiday.date, currentLocale)}
                  </td>
                  <td className="px-4 py-2 text-primary">{localName(holiday, currentLocale)}</td>
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
                      {/* A statutory day is a whole day by law, so its length is
                          not the company's to change either — halving one here
                          would quietly raise ten people's target for that day.
                          The half days that do exist by agreement, 24 and 31
                          December, are granted rather than statutory and keep
                          their toggle. */}
                      {holiday.is_statutory ? null : (
                        <HrRowAction
                          icon={
                            isHalf(holiday.day_fraction) ? (
                              <Circle className="size-4" />
                            ) : (
                              <Contrast className="size-4" />
                            )
                          }
                          label={
                            isHalf(holiday.day_fraction) ? t("hr.holidays.make_whole") : t("hr.holidays.make_half")
                          }
                          subject={localName(holiday, currentLocale)}
                          disabled={isBusy}
                          onClick={() => void handleToggleHalf(holiday)}
                        />
                      )}
                      {/* A statutory day is not the company's to remove. */}
                      {holiday.is_statutory ? null : (
                        <HrRowAction
                          icon={<Trash2 className="size-4" />}
                          label={t("hr.holidays.remove")}
                          subject={localName(holiday, currentLocale)}
                          danger
                          disabled={isBusy}
                          onClick={() => setRemoving(holiday)}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
