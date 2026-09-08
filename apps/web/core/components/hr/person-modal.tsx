/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import {
  EHrArrangement,
  type THrContract,
  type THrEmploymentProfile,
  type THrWorkSchedule,
} from "@/services/hr.service";
// local imports
import { formatMinutes, parseDuration } from "./utils";

const WEEKDAYS = [
  { key: "monday_minutes", label: "hr.people.weekday.monday" },
  { key: "tuesday_minutes", label: "hr.people.weekday.tuesday" },
  { key: "wednesday_minutes", label: "hr.people.weekday.wednesday" },
  { key: "thursday_minutes", label: "hr.people.weekday.thursday" },
  { key: "friday_minutes", label: "hr.people.weekday.friday" },
  { key: "saturday_minutes", label: "hr.people.weekday.saturday" },
  { key: "sunday_minutes", label: "hr.people.weekday.sunday" },
] as const;

const ARRANGEMENTS = [
  EHrArrangement.ONSITE_FULL_TIME,
  EHrArrangement.ONSITE_PART_TIME,
  EHrArrangement.REMOTE_FULL_TIME_INVOICING,
  EHrArrangement.REMOTE_PART_TIME_INVOICING,
];

export type TPersonDraft = {
  profile: Partial<THrEmploymentProfile>;
  contract: Partial<THrContract>;
  schedule: Partial<THrWorkSchedule>;
};

type TProps = {
  isOpen: boolean;
  person: THrEmploymentProfile | null;
  contract: THrContract | null;
  schedule: THrWorkSchedule | null;
  isBusy: boolean;
  onClose: () => void;
  onSave: (draft: TPersonDraft) => void;
};

/**
 * Everything that decides what a person's month comes to.
 *
 * The three records are edited together rather than on separate screens because
 * they are only meaningful together: terms without a schedule owe hours on no
 * particular day, and a schedule without terms is a pattern nobody is held to.
 * Someone setting a person up half way would produce months that compute, and
 * compute wrongly.
 */
export const HrPersonModal = ({ isOpen, person, contract, schedule, isBusy, onClose, onSave }: TProps) => {
  const { t } = useTranslation();

  const [hireDate, setHireDate] = useState("");
  const [timezone, setTimezone] = useState("Europe/Vienna");
  const [isManager, setIsManager] = useState(false);
  const [crmStaffId, setCrmStaffId] = useState("");
  const [arrangement, setArrangement] = useState<EHrArrangement>(EHrArrangement.ONSITE_FULL_TIME);
  const [recordsTarget, setRecordsTarget] = useState(true);
  const [validFrom, setValidFrom] = useState("");
  const [days, setDays] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<string | null>(null);

  // Seeded from what these things are, not from the objects holding them. The
  // terms and the schedule are fetched, so the objects are new on every
  // revalidation while the ids are not — depending on the objects emptied the
  // form under whoever was filling it in. An id still moves when a different
  // person is opened, or when the terms arrive for the first time, which is
  // when seeding is wanted.
  useEffect(() => {
    if (!isOpen) return;
    setProblem(null);
    setHireDate(person?.hire_date ?? "");
    setTimezone(person?.timezone || "Europe/Vienna");
    setIsManager(person?.is_hr_manager ?? false);
    setCrmStaffId(person?.crm_staff_id ? String(person.crm_staff_id) : "");
    setArrangement((contract?.arrangement as EHrArrangement) ?? EHrArrangement.ONSITE_FULL_TIME);
    setRecordsTarget(contract?.records_target_hours ?? true);
    setValidFrom(contract?.valid_from ?? person?.hire_date ?? "");
    setDays(
      Object.fromEntries(
        WEEKDAYS.map(({ key }) => {
          const minutes = schedule?.[key] ?? 0;
          return [key, minutes ? formatMinutes(minutes) : ""];
        })
      )
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, person?.id, contract?.id, schedule?.id]);

  const weekMinutes = WEEKDAYS.reduce((total, { key }) => total + (parseDuration(days[key] ?? "") ?? 0), 0);

  const handleSave = () => {
    // A day typed but unreadable must not quietly become a day off.
    const unreadable = WEEKDAYS.find(({ key }) => {
      const raw = (days[key] ?? "").trim();
      return raw !== "" && parseDuration(raw) === null;
    });
    if (unreadable) {
      setProblem(t("hr.people.errors.bad_duration"));
      return;
    }
    if (!hireDate) {
      setProblem(t("hr.people.errors.hire_date_required"));
      return;
    }
    if (weekMinutes === 0) {
      setProblem(t("hr.people.errors.week_required"));
      return;
    }
    // A typo here reads as a whole number and comes out as NaN, which becomes
    // null on the way to the server — and null is how the field is deliberately
    // cleared. So a mistyped id did not fail: it silently put the person back on
    // the email match, and nothing on any screen said their hours had stopped
    // reaching the CRM under the id somebody had chosen for them.
    const staffId = crmStaffId.trim();
    if (staffId !== "" && !/^[1-9][0-9]*$/.test(staffId)) {
      setProblem(t("hr.people.errors.bad_crm_staff_id"));
      return;
    }

    onSave({
      profile: {
        hire_date: hireDate,
        timezone,
        is_hr_manager: isManager,
        // Empty clears it, which puts them back on the email match. Anything
        // else has been checked above, so it is a number by the time it is sent.
        crm_staff_id: staffId === "" ? null : Number(staffId),
      },
      contract: {
        valid_from: validFrom || hireDate,
        arrangement,
        records_target_hours: recordsTarget,
        weekly_minutes: weekMinutes || null,
      },
      schedule: {
        valid_from: validFrom || hireDate,
        ...Object.fromEntries(WEEKDAYS.map(({ key }) => [key, parseDuration(days[key] ?? "") ?? 0])),
      },
    });
  };

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXXL}>
      <div className="flex max-h-[80vh] flex-col gap-5 overflow-y-auto p-5">
        <div>
          <h3 className="text-16 font-medium text-primary">{person?.member_display_name || person?.member_email}</h3>
          <p className="text-13 text-tertiary">{t("hr.people.modal_hint")}</p>
        </div>

        <section className="flex flex-col gap-3">
          <h4 className="text-13 font-medium text-secondary">{t("hr.people.section_person")}</h4>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("hr.people.hire_date")}>
              <input
                type="date"
                value={hireDate}
                onChange={(e) => setHireDate(e.target.value)}
                className={inputClass}
              />
            </Field>
            <Field label={t("hr.people.timezone")}>
              <input value={timezone} onChange={(e) => setTimezone(e.target.value)} className={inputClass} />
            </Field>
          </div>
          <Field label={t("hr.people.crm_staff_id")}>
            <input
              value={crmStaffId}
              inputMode="numeric"
              placeholder={t("hr.people.crm_staff_id_placeholder")}
              onChange={(e) => setCrmStaffId(e.target.value)}
              className={inputClass}
            />
            <p className="mt-1 text-13 text-tertiary">
              {person?.crm_link === "set"
                ? t("hr.people.crm_link.set")
                : person?.crm_link === "email"
                  ? t("hr.people.crm_link.email")
                  : t("hr.people.crm_link.none")}
            </p>
          </Field>

          <label className="flex items-center gap-2 text-13 text-secondary">
            <input type="checkbox" checked={isManager} onChange={(e) => setIsManager(e.target.checked)} />
            {t("hr.people.is_manager")}
          </label>
        </section>

        <section className="flex flex-col gap-3">
          <h4 className="text-13 font-medium text-secondary">{t("hr.people.section_terms")}</h4>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("hr.people.arrangement")}>
              <select
                value={arrangement}
                onChange={(e) => setArrangement(e.target.value as EHrArrangement)}
                className={inputClass}
              >
                {ARRANGEMENTS.map((value) => (
                  <option key={value} value={value}>
                    {t(`hr.arrangement.${value}`)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("hr.people.valid_from")}>
              <input
                type="date"
                value={validFrom}
                onChange={(e) => setValidFrom(e.target.value)}
                className={inputClass}
              />
            </Field>
          </div>
          <label className="flex items-start gap-2 text-13 text-secondary">
            <input
              type="checkbox"
              checked={recordsTarget}
              onChange={(e) => setRecordsTarget(e.target.checked)}
              className="mt-1"
            />
            <span>
              {t("hr.people.records_target")}
              <span className="block text-13 text-tertiary">{t("hr.people.records_target_hint")}</span>
            </span>
          </label>
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between">
            <h4 className="text-13 font-medium text-secondary">{t("hr.people.section_schedule")}</h4>
            <span className="text-13 text-tertiary">
              {t("hr.people.week_total", { duration: formatMinutes(weekMinutes) })}
            </span>
          </div>
          <p className="text-13 text-tertiary">{t("hr.people.schedule_hint")}</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
            {WEEKDAYS.map(({ key, label }) => (
              <Field key={key} label={t(label)}>
                <input
                  value={days[key] ?? ""}
                  onChange={(e) => setDays((prev) => ({ ...prev, [key]: e.target.value }))}
                  placeholder="0:00"
                  className={cn(inputClass, "text-right tabular-nums")}
                />
              </Field>
            ))}
          </div>
        </section>

        {problem ? <p className="text-13 text-danger-primary">{problem}</p> : null}

        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("hr.people.cancel")}
          </Button>
          <Button variant="primary" size="lg" loading={isBusy} onClick={handleSave}>
            {t("hr.people.save")}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
};

const inputClass =
  "border-subtle bg-layer-1 text-primary focus:border-accent-strong w-full rounded-md border px-3 py-1.5 text-13 outline-none";

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="flex flex-col gap-1">
    <span className="text-13 font-medium text-tertiary">{label}</span>
    {children}
  </label>
);
