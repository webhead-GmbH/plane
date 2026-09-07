/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo, useRef, useState } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import {
  EHrGranularity,
  EHrHalf,
  type THrAbsence,
  type THrAbsenceType,
  type THrEmploymentProfile,
} from "@/services/hr.service";
// local imports
import { localName, parseDuration } from "./utils";

export type TAbsenceDraft = {
  profile_id: string;
  absence_type: string;
  start_date: string;
  end_date: string;
  granularity: EHrGranularity;
  start_half: EHrHalf | null;
  end_half: EHrHalf | null;
  minutes_per_day: number | null;
  reason: string;
};

type TProps = {
  isOpen: boolean;
  /** The absence being changed, or null when a new one is being recorded. */
  absence: THrAbsence | null;
  people: THrEmploymentProfile[];
  types: THrAbsenceType[];
  /** Fixed when recording for one person, so the picker is not shown at all. */
  fixedProfileId?: string;
  isBusy: boolean;
  onClose: () => void;
  onSave: (draft: TAbsenceDraft) => void;
};

const HALVES = [EHrHalf.MORNING, EHrHalf.AFTERNOON];

const HALF_KEY: Record<number, string> = {
  [EHrHalf.MORNING]: "morning",
  [EHrHalf.AFTERNOON]: "afternoon",
};

const GRANULARITY_KEY: Record<number, string> = {
  [EHrGranularity.FULL_DAY]: "full_day",
  [EHrGranularity.HALF_DAY]: "half_day",
  [EHrGranularity.HOURS]: "hours",
};

const today = () => new Date().toISOString().slice(0, 10);

/**
 * Record a stretch of time away.
 *
 * Half days are offered only at the two ends of a range, which is where they
 * actually happen: somebody leaves at midday on the Friday, or comes back at
 * midday on the Monday. A half day in the middle of a week is a range of its own,
 * and asking for one here would invite a record nobody could read back.
 *
 * The hours option exists for the afternoon at the doctor — a fixed number of
 * minutes on each day of the range, rather than a fraction of whatever that day
 * happened to be scheduled for.
 */
export const HrAbsenceModal = ({ isOpen, absence, people, types, fixedProfileId, isBusy, onClose, onSave }: TProps) => {
  const { t, currentLocale } = useTranslation();

  const activeTypes = useMemo(
    () => types.filter((type) => type.is_active || type.id === absence?.absence_type),
    [types, absence]
  );

  const [profileId, setProfileId] = useState("");
  const [typeId, setTypeId] = useState("");
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(today);
  const [granularity, setGranularity] = useState<EHrGranularity>(EHrGranularity.FULL_DAY);
  const [startHalf, setStartHalf] = useState<EHrHalf>(EHrHalf.AFTERNOON);
  const [endHalf, setEndHalf] = useState<EHrHalf>(EHrHalf.MORNING);
  const [hours, setHours] = useState("");
  const [reason, setReason] = useState("");

  // What the boxes were last filled from. Seeding is once per opening: the
  // effect below also watches the lists the defaults come from, and SWR hands
  // back a fresh array on every revalidation — so anything on the page
  // refreshing emptied the form somebody was in the middle of filling in.
  const seededFrom = useRef<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      seededFrom.current = null;
      return;
    }
    // Wait for the list the default kind comes from, so a slow load still ends
    // up seeded rather than seeded with nothing.
    const seed = absence?.id ?? "new";
    if (seededFrom.current === seed || activeTypes.length === 0) return;
    seededFrom.current = seed;

    setProfileId(absence?.profile ?? fixedProfileId ?? people[0]?.id ?? "");
    setTypeId(absence?.absence_type ?? activeTypes[0]?.id ?? "");
    setStartDate(absence?.start_date ?? today());
    setEndDate(absence?.end_date ?? today());
    setGranularity(absence?.granularity ?? EHrGranularity.FULL_DAY);
    setStartHalf(absence?.start_half ?? EHrHalf.AFTERNOON);
    setEndHalf(absence?.end_half ?? EHrHalf.MORNING);
    setHours(absence?.minutes_per_day ? String(absence.minutes_per_day / 60) : "");
    setReason(absence?.reason ?? "");
  }, [isOpen, absence, fixedProfileId, people, activeTypes]);

  // A range that ends before it starts is the commonest slip on these two fields,
  // and it produces an absence of no days rather than an error, so it is caught here.
  const backwards = endDate < startDate;
  const isOneDay = startDate === endDate;
  const minutesPerDay = granularity === EHrGranularity.HOURS ? parseDuration(hours) : null;
  const hoursMissing = granularity === EHrGranularity.HOURS && (minutesPerDay === null || minutesPerDay <= 0);

  const canSave = Boolean(profileId) && Boolean(typeId) && !backwards && !hoursMissing && !isBusy;

  const handleSave = () => {
    if (!canSave) return;

    onSave({
      profile_id: profileId,
      absence_type: typeId,
      start_date: startDate,
      end_date: endDate,
      granularity,
      // Halves belong to a half-day absence and to nothing else. A one-day
      // absence is both ends at once, so it carries the opening half alone.
      start_half: granularity === EHrGranularity.HALF_DAY ? startHalf : null,
      end_half: granularity === EHrGranularity.HALF_DAY && !isOneDay ? endHalf : null,
      minutes_per_day: minutesPerDay,
      reason: reason.trim(),
    });
  };

  const field = "border-subtle bg-layer-1 text-primary w-full rounded-md border px-3 py-1.5 text-13";
  const label = "text-tertiary mb-1 block text-13 font-medium";

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XL}>
      <div className="flex flex-col gap-4 p-5">
        <div>
          <h3 className="text-14 font-semibold text-primary">
            {absence ? t("hr.absences.modal.edit_title") : t("hr.absences.modal.title")}
          </h3>
          <p className="text-13 text-tertiary">{t("hr.absences.modal.subtitle")}</p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {!fixedProfileId && (
            <div className="sm:col-span-2">
              <label className={label} htmlFor="hr-absence-person">
                {t("hr.absences.modal.person")}
              </label>
              <select
                id="hr-absence-person"
                className={field}
                value={profileId}
                disabled={Boolean(absence)}
                onChange={(event) => setProfileId(event.target.value)}
              >
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.member_display_name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="sm:col-span-2">
            <label className={label} htmlFor="hr-absence-type">
              {t("hr.absences.modal.type")}
            </label>
            <select
              id="hr-absence-type"
              className={field}
              value={typeId}
              onChange={(event) => setTypeId(event.target.value)}
            >
              {activeTypes.length === 0 && <option value="">{t("hr.absences.modal.no_types")}</option>}
              {activeTypes.map((type) => (
                <option key={type.id} value={type.id}>
                  {localName(type, currentLocale) || type.code}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={label} htmlFor="hr-absence-from">
              {t("hr.absences.modal.from")}
            </label>
            <input
              id="hr-absence-from"
              type="date"
              className={field}
              value={startDate}
              onChange={(event) => {
                setStartDate(event.target.value);
                // Moving the start past the end almost always means a one-day
                // absence, so the end follows rather than becoming invalid.
                if (event.target.value > endDate) setEndDate(event.target.value);
              }}
            />
          </div>

          <div>
            <label className={label} htmlFor="hr-absence-to">
              {t("hr.absences.modal.to")}
            </label>
            <input
              id="hr-absence-to"
              type="date"
              className={cn(field, backwards && "border-danger-strong")}
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
            {backwards && <p className="mt-1 text-13 text-danger-primary">{t("hr.absences.modal.backwards")}</p>}
          </div>

          <div className="sm:col-span-2">
            <label className={label} htmlFor="hr-absence-granularity">
              {t("hr.absences.modal.granularity")}
            </label>
            <select
              id="hr-absence-granularity"
              className={field}
              value={granularity}
              onChange={(event) => setGranularity(Number(event.target.value) as EHrGranularity)}
            >
              {[EHrGranularity.FULL_DAY, EHrGranularity.HALF_DAY, EHrGranularity.HOURS].map((option) => (
                <option key={option} value={option}>
                  {t(`hr.absences.granularity.${GRANULARITY_KEY[option]}`)}
                </option>
              ))}
            </select>
          </div>

          {granularity === EHrGranularity.HALF_DAY && (
            <>
              <div>
                <label className={label} htmlFor="hr-absence-start-half">
                  {isOneDay ? t("hr.absences.modal.which_half") : t("hr.absences.modal.first_day")}
                </label>
                <select
                  id="hr-absence-start-half"
                  className={field}
                  value={startHalf}
                  onChange={(event) => setStartHalf(Number(event.target.value) as EHrHalf)}
                >
                  {HALVES.map((half) => (
                    <option key={half} value={half}>
                      {t(`hr.absences.half.${HALF_KEY[half]}`)}
                    </option>
                  ))}
                </select>
              </div>

              {!isOneDay && (
                <div>
                  <label className={label} htmlFor="hr-absence-end-half">
                    {t("hr.absences.modal.last_day")}
                  </label>
                  <select
                    id="hr-absence-end-half"
                    className={field}
                    value={endHalf}
                    onChange={(event) => setEndHalf(Number(event.target.value) as EHrHalf)}
                  >
                    {HALVES.map((half) => (
                      <option key={half} value={half}>
                        {t(`hr.absences.half.${HALF_KEY[half]}`)}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </>
          )}

          {granularity === EHrGranularity.HOURS && (
            <div className="sm:col-span-2">
              <label className={label} htmlFor="hr-absence-hours">
                {t("hr.absences.modal.hours_each_day")}
              </label>
              <input
                id="hr-absence-hours"
                className={cn(field, hoursMissing && hours !== "" && "border-danger-strong")}
                value={hours}
                placeholder={t("hr.absences.modal.hours_placeholder")}
                onChange={(event) => setHours(event.target.value)}
              />
              <p className={cn("mt-1 text-13", hoursMissing && hours !== "" ? "text-danger-primary" : "text-tertiary")}>
                {hoursMissing && hours !== ""
                  ? t("hr.absences.modal.hours_unreadable")
                  : t("hr.absences.modal.hours_hint")}
              </p>
            </div>
          )}

          <div className="sm:col-span-2">
            <label className={label} htmlFor="hr-absence-reason">
              {t("hr.absences.modal.note")}
            </label>
            <input
              id="hr-absence-reason"
              className={field}
              value={reason}
              placeholder={t("hr.absences.modal.note_placeholder")}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button variant="primary" size="lg" disabled={!canSave} onClick={handleSave}>
            {absence ? t("common.save_changes") : t("hr.absences.modal.record")}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
};
