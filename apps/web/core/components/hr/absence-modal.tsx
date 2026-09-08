/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
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

const fieldClass = "border-subtle bg-layer-1 text-primary w-full rounded-md border px-3 py-1.5 text-13";
const labelClass = "text-tertiary mb-1 block text-13 font-medium";

const today = () => new Date().toISOString().slice(0, 10);

/**
 * Nothing chosen. A dialog that opens ahead of the kinds of absence waits like
 * this: a person and a kind already filled in would be an answer nobody gave,
 * and one that could be saved as it stands.
 */
const nothingChosen = () => ({
  profileId: "",
  typeId: "",
  startDate: today(),
  endDate: today(),
  granularity: EHrGranularity.FULL_DAY,
  startHalf: EHrHalf.AFTERNOON,
  endHalf: EHrHalf.MORNING,
  hours: "",
  reason: "",
});

/** Everything the dialog asks about, answered and saved as one thing. */
type TTyped = ReturnType<typeof nothingChosen>;

/** What the boxes say before anybody touches them: the absence being changed, or a fresh one. */
const asTyped = (
  absence: THrAbsence | null,
  people: THrEmploymentProfile[],
  activeTypes: THrAbsenceType[],
  fixedProfileId?: string
): TTyped => ({
  profileId: absence?.profile ?? fixedProfileId ?? people[0]?.id ?? "",
  typeId: absence?.absence_type ?? activeTypes[0]?.id ?? "",
  startDate: absence?.start_date ?? today(),
  endDate: absence?.end_date ?? today(),
  granularity: absence?.granularity ?? EHrGranularity.FULL_DAY,
  startHalf: absence?.start_half ?? EHrHalf.AFTERNOON,
  endHalf: absence?.end_half ?? EHrHalf.MORNING,
  hours: absence?.minutes_per_day ? String(absence.minutes_per_day / 60) : "",
  reason: absence?.reason ?? "",
});

/** A fixed number of minutes on each day of the range, which only an absence counted in hours has. */
const minutesEachDay = (granularity: EHrGranularity, hours: string) =>
  granularity === EHrGranularity.HOURS ? parseDuration(hours) : null;

/** Hours were asked for and what was typed is not a length of time. */
const hoursUnreadable = (granularity: EHrGranularity, minutesPerDay: number | null) =>
  granularity === EHrGranularity.HOURS && (minutesPerDay === null || minutesPerDay <= 0);

/**
 * Halves belong to a half-day absence and to nothing else. A one-day absence is
 * both ends at once, so it carries the opening half alone.
 */
const halvesFor = (granularity: EHrGranularity, isOneDay: boolean, startHalf: EHrHalf, endHalf: EHrHalf) => ({
  start_half: granularity === EHrGranularity.HALF_DAY ? startHalf : null,
  end_half: granularity === EHrGranularity.HALF_DAY && !isOneDay ? endHalf : null,
});

/**
 * Names the sitting of the dialog the boxes were built for.
 *
 * A dialog that has been closed is still on screen while it fades, and by then
 * the row it was opened on has already been forgotten; the name stays as it was
 * so the panel goes on showing what somebody was looking at until it has gone.
 * Opening it again is a fresh sitting, even on the same absence and even before
 * that fade is over, and gets boxes filled in from the record rather than
 * whatever the last attempt left in them.
 */
const useSitting = (isOpen: boolean, absence: THrAbsence | null) => {
  const [openings, setOpenings] = useState(0);
  const [wasOpen, setWasOpen] = useState(isOpen);
  const [name, setName] = useState("");

  if (wasOpen !== isOpen) {
    setWasOpen(isOpen);
    if (isOpen) {
      setOpenings(openings + 1);
      setName(`${openings + 1}:${absence?.id ?? "new"}`);
    }
  }

  return name;
};

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
  const activeTypes = useMemo(
    () => types.filter((type) => type.is_active || type.id === absence?.absence_type),
    [types, absence]
  );
  const sitting = useSitting(isOpen, absence);

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XL}>
      {/* One dialog per sitting: opening it on another absence, or opening it
          again on the same one, builds a new one with the boxes filled in from
          the record. Anything on the page behind refreshing hands back new
          arrays and leaves whoever is halfway through filling this in alone. */}
      <AbsenceForm
        key={sitting}
        absence={absence}
        people={people}
        activeTypes={activeTypes}
        fixedProfileId={fixedProfileId}
        isBusy={isBusy}
        onClose={onClose}
        onSave={onSave}
      />
    </ModalCore>
  );
};

const AbsenceForm = ({
  absence,
  people,
  activeTypes,
  fixedProfileId,
  isBusy,
  onClose,
  onSave,
}: {
  absence: THrAbsence | null;
  people: THrEmploymentProfile[];
  activeTypes: THrAbsenceType[];
  fixedProfileId?: string;
  isBusy: boolean;
  onClose: () => void;
  onSave: (draft: TAbsenceDraft) => void;
}) => {
  const [typed, setTyped] = useState<TTyped>(nothingChosen);
  const [waiting, setWaiting] = useState(true);
  const edit = (answer: Partial<TTyped>) => setTyped((current) => ({ ...current, ...answer }));

  // Filled in as soon as there is a kind of absence to choose, and once only:
  // the lists these defaults come from are fetched, so a refresh hands back new
  // arrays, and filling the boxes in again on one of those would take away
  // whatever somebody had put in them.
  if (waiting && activeTypes.length > 0) {
    setWaiting(false);
    setTyped(asTyped(absence, people, activeTypes, fixedProfileId));
  }

  const { profileId, typeId, startDate, endDate, granularity, startHalf, endHalf, hours, reason } = typed;

  // A range that ends before it starts is the commonest slip on these two fields,
  // and it produces an absence of no days rather than an error, so it is caught here.
  const backwards = endDate < startDate;
  const isOneDay = startDate === endDate;
  const minutesPerDay = minutesEachDay(granularity, hours);
  const hoursMissing = hoursUnreadable(granularity, minutesPerDay);

  const canSave = Boolean(profileId) && Boolean(typeId) && !backwards && !hoursMissing && !isBusy;

  // Moving the start past the end almost always means a one-day absence, so the
  // end follows rather than becoming invalid.
  const handleStartDate = (value: string) =>
    edit(value > endDate ? { startDate: value, endDate: value } : { startDate: value });

  const handleSave = () => {
    if (!canSave) return;

    onSave({
      profile_id: profileId,
      absence_type: typeId,
      start_date: startDate,
      end_date: endDate,
      granularity,
      ...halvesFor(granularity, isOneDay, startHalf, endHalf),
      minutes_per_day: minutesPerDay,
      reason: reason.trim(),
    });
  };

  return (
    <div className="flex flex-col gap-4 p-5">
      <AbsenceHeading isEdit={Boolean(absence)} />

      <div className="grid gap-3 sm:grid-cols-2">
        {!fixedProfileId && (
          <PersonField
            people={people}
            profileId={profileId}
            isSettled={Boolean(absence)}
            onChange={(value) => edit({ profileId: value })}
          />
        )}

        <TypeField activeTypes={activeTypes} typeId={typeId} onChange={(value) => edit({ typeId: value })} />

        <DateRangeFields
          startDate={startDate}
          endDate={endDate}
          backwards={backwards}
          onStartDate={handleStartDate}
          onEndDate={(value) => edit({ endDate: value })}
        />

        <DayLengthFields
          granularity={granularity}
          isOneDay={isOneDay}
          startHalf={startHalf}
          endHalf={endHalf}
          hours={hours}
          hoursMissing={hoursMissing}
          onGranularity={(value) => edit({ granularity: value })}
          onStartHalf={(value) => edit({ startHalf: value })}
          onEndHalf={(value) => edit({ endHalf: value })}
          onHours={(value) => edit({ hours: value })}
        />

        <NoteField reason={reason} onChange={(value) => edit({ reason: value })} />
      </div>

      <AbsenceFooter isEdit={Boolean(absence)} canSave={canSave} onClose={onClose} onSave={handleSave} />
    </div>
  );
};

const AbsenceHeading = ({ isEdit }: { isEdit: boolean }) => {
  const { t } = useTranslation();

  return (
    <div>
      <h3 className="text-14 font-semibold text-primary">
        {isEdit ? t("hr.absences.modal.edit_title") : t("hr.absences.modal.title")}
      </h3>
      <p className="text-13 text-tertiary">{t("hr.absences.modal.subtitle")}</p>
    </div>
  );
};

/** Whose absence it is, settled once it exists: moving one to somebody else is a different record. */
const PersonField = ({
  people,
  profileId,
  isSettled,
  onChange,
}: {
  people: THrEmploymentProfile[];
  profileId: string;
  isSettled: boolean;
  onChange: (value: string) => void;
}) => {
  const { t } = useTranslation();

  return (
    <div className="sm:col-span-2">
      <label className={labelClass} htmlFor="hr-absence-person">
        {t("hr.absences.modal.person")}
      </label>
      <select
        id="hr-absence-person"
        className={fieldClass}
        value={profileId}
        disabled={isSettled}
        onChange={(event) => onChange(event.target.value)}
      >
        {people.map((person) => (
          <option key={person.id} value={person.id}>
            {person.member_display_name}
          </option>
        ))}
      </select>
    </div>
  );
};

/** The kind of absence. A kind that has been retired still names the absences already recorded under it. */
const TypeField = ({
  activeTypes,
  typeId,
  onChange,
}: {
  activeTypes: THrAbsenceType[];
  typeId: string;
  onChange: (value: string) => void;
}) => {
  const { t, currentLocale } = useTranslation();

  return (
    <div className="sm:col-span-2">
      <label className={labelClass} htmlFor="hr-absence-type">
        {t("hr.absences.modal.type")}
      </label>
      <select
        id="hr-absence-type"
        className={fieldClass}
        value={typeId}
        onChange={(event) => onChange(event.target.value)}
      >
        {activeTypes.length === 0 && <option value="">{t("hr.absences.modal.no_types")}</option>}
        {activeTypes.map((type) => (
          <option key={type.id} value={type.id}>
            {localName(type, currentLocale) || type.code}
          </option>
        ))}
      </select>
    </div>
  );
};

const DateRangeFields = ({
  startDate,
  endDate,
  backwards,
  onStartDate,
  onEndDate,
}: {
  startDate: string;
  endDate: string;
  backwards: boolean;
  onStartDate: (value: string) => void;
  onEndDate: (value: string) => void;
}) => {
  const { t } = useTranslation();

  return (
    <>
      <div>
        <label className={labelClass} htmlFor="hr-absence-from">
          {t("hr.absences.modal.from")}
        </label>
        <input
          id="hr-absence-from"
          type="date"
          className={fieldClass}
          value={startDate}
          onChange={(event) => onStartDate(event.target.value)}
        />
      </div>

      <div>
        <label className={labelClass} htmlFor="hr-absence-to">
          {t("hr.absences.modal.to")}
        </label>
        <input
          id="hr-absence-to"
          type="date"
          className={cn(fieldClass, backwards && "border-danger-strong")}
          value={endDate}
          onChange={(event) => onEndDate(event.target.value)}
        />
        {backwards && <p className="mt-1 text-13 text-danger-primary">{t("hr.absences.modal.backwards")}</p>}
      </div>
    </>
  );
};

/** How much of each day is away, and whatever that choice still needs asking about. */
const DayLengthFields = ({
  granularity,
  isOneDay,
  startHalf,
  endHalf,
  hours,
  hoursMissing,
  onGranularity,
  onStartHalf,
  onEndHalf,
  onHours,
}: {
  granularity: EHrGranularity;
  isOneDay: boolean;
  startHalf: EHrHalf;
  endHalf: EHrHalf;
  hours: string;
  hoursMissing: boolean;
  onGranularity: (value: EHrGranularity) => void;
  onStartHalf: (value: EHrHalf) => void;
  onEndHalf: (value: EHrHalf) => void;
  onHours: (value: string) => void;
}) => {
  const { t } = useTranslation();

  return (
    <>
      <div className="sm:col-span-2">
        <label className={labelClass} htmlFor="hr-absence-granularity">
          {t("hr.absences.modal.granularity")}
        </label>
        <select
          id="hr-absence-granularity"
          className={fieldClass}
          value={granularity}
          onChange={(event) => onGranularity(Number(event.target.value) as EHrGranularity)}
        >
          {[EHrGranularity.FULL_DAY, EHrGranularity.HALF_DAY, EHrGranularity.HOURS].map((option) => (
            <option key={option} value={option}>
              {t(`hr.absences.granularity.${GRANULARITY_KEY[option]}`)}
            </option>
          ))}
        </select>
      </div>

      {granularity === EHrGranularity.HALF_DAY && (
        <HalfDayFields
          isOneDay={isOneDay}
          startHalf={startHalf}
          endHalf={endHalf}
          onStartHalf={onStartHalf}
          onEndHalf={onEndHalf}
        />
      )}

      {granularity === EHrGranularity.HOURS && (
        <HoursField hours={hours} hoursMissing={hoursMissing} onChange={onHours} />
      )}
    </>
  );
};

/** Which half of the day, at each end of the range. One day away is one end, so it is asked once. */
const HalfDayFields = ({
  isOneDay,
  startHalf,
  endHalf,
  onStartHalf,
  onEndHalf,
}: {
  isOneDay: boolean;
  startHalf: EHrHalf;
  endHalf: EHrHalf;
  onStartHalf: (value: EHrHalf) => void;
  onEndHalf: (value: EHrHalf) => void;
}) => {
  const { t } = useTranslation();

  return (
    <>
      <div>
        <label className={labelClass} htmlFor="hr-absence-start-half">
          {isOneDay ? t("hr.absences.modal.which_half") : t("hr.absences.modal.first_day")}
        </label>
        <select
          id="hr-absence-start-half"
          className={fieldClass}
          value={startHalf}
          onChange={(event) => onStartHalf(Number(event.target.value) as EHrHalf)}
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
          <label className={labelClass} htmlFor="hr-absence-end-half">
            {t("hr.absences.modal.last_day")}
          </label>
          <select
            id="hr-absence-end-half"
            className={fieldClass}
            value={endHalf}
            onChange={(event) => onEndHalf(Number(event.target.value) as EHrHalf)}
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
  );
};

const HoursField = ({
  hours,
  hoursMissing,
  onChange,
}: {
  hours: string;
  hoursMissing: boolean;
  onChange: (value: string) => void;
}) => {
  const { t } = useTranslation();

  // An empty box is somebody who has not answered yet rather than somebody who
  // answered badly, so the hint stays a hint until there is something to read.
  const unreadable = hoursMissing && hours !== "";

  return (
    <div className="sm:col-span-2">
      <label className={labelClass} htmlFor="hr-absence-hours">
        {t("hr.absences.modal.hours_each_day")}
      </label>
      <input
        id="hr-absence-hours"
        className={cn(fieldClass, unreadable && "border-danger-strong")}
        value={hours}
        placeholder={t("hr.absences.modal.hours_placeholder")}
        onChange={(event) => onChange(event.target.value)}
      />
      <p className={cn("mt-1 text-13", unreadable ? "text-danger-primary" : "text-tertiary")}>
        {unreadable ? t("hr.absences.modal.hours_unreadable") : t("hr.absences.modal.hours_hint")}
      </p>
    </div>
  );
};

const NoteField = ({ reason, onChange }: { reason: string; onChange: (value: string) => void }) => {
  const { t } = useTranslation();

  return (
    <div className="sm:col-span-2">
      <label className={labelClass} htmlFor="hr-absence-reason">
        {t("hr.absences.modal.note")}
      </label>
      <input
        id="hr-absence-reason"
        className={fieldClass}
        value={reason}
        placeholder={t("hr.absences.modal.note_placeholder")}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
};

const AbsenceFooter = ({
  isEdit,
  canSave,
  onClose,
  onSave,
}: {
  isEdit: boolean;
  canSave: boolean;
  onClose: () => void;
  onSave: () => void;
}) => {
  const { t } = useTranslation();

  return (
    <div className="flex items-center justify-end gap-2">
      <Button variant="secondary" size="lg" onClick={onClose}>
        {t("common.cancel")}
      </Button>
      <Button variant="primary" size="lg" disabled={!canSave} onClick={onSave}>
        {isEdit ? t("common.save_changes") : t("hr.absences.modal.record")}
      </Button>
    </div>
  );
};
