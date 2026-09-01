/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Link } from "react-router";
import { CalendarClock, Plus, UserMinus } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { Loader } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import { HrService, type THrContract, type THrEmploymentProfile } from "@/services/hr.service";
// local imports
import { HrAddPersonModal } from "./add-person-modal";
import { HrPersonModal, type TPersonDraft } from "./person-modal";
import { formatMinutes } from "./utils";

const hrService = new HrService();

/**
 * The people the company employs, and the terms each of them works under.
 *
 * Reached from the team's month rather than from workspace settings. Looking
 * after the team is a property of the person here, deliberately not the same
 * thing as administering a workspace — filing this under workspace settings
 * would have let an administrator in and kept the actual manager out.
 */
export const HrPeopleRoot = observer(function HrPeopleRoot({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<THrEmploymentProfile | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const { data: people, isLoading, error, mutate } = useSWR("HR_EMPLOYEES", () => hrService.employees());
  const { data: candidates, mutate: refreshCandidates } = useSWR("HR_CANDIDATES", () => hrService.candidates());
  const { data: schedules, mutate: refreshSchedules } = useSWR("HR_SCHEDULES", () => hrService.schedules());
  const { data: contracts, mutate: refreshContracts } = useSWR(editing ? `HR_CONTRACTS_${editing.id}` : null, () =>
    editing ? hrService.contracts(editing.id) : null
  );

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.people.toasts.refused"),
      message: (failure as { error?: string })?.error ?? t("hr.people.toasts.try_again"),
    });

  const handleAdd = async (memberId: string, hireDate: string) => {
    setIsBusy(true);
    try {
      await hrService.createEmployee({ member: memberId, hire_date: hireDate, timezone: "Europe/Vienna" });
      await Promise.all([mutate(), refreshCandidates()]);
      setAdding(false);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.people.toasts.added") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleSave = async (draft: TPersonDraft) => {
    if (!editing) return;
    setIsBusy(true);
    try {
      await hrService.updateEmployee(editing.id, draft.profile);

      // One set of terms and one schedule per stretch of time. Whichever is
      // already in force from the same date is amended; anything else would
      // leave two records covering the same day and no way to say which applies.
      const existingContract = (contracts ?? []).find((row) => row.valid_from === draft.contract.valid_from);
      if (existingContract) await hrService.updateContract(editing.id, existingContract.id, draft.contract);
      else await hrService.createContract(editing.id, draft.contract);

      const own = (schedules ?? []).find(
        (row) => row.profile === editing.id && row.valid_from === draft.schedule.valid_from
      );
      if (own) await hrService.updateSchedule(own.id, draft.schedule);
      else await hrService.createSchedule({ ...draft.schedule, profile: editing.id });

      await Promise.all([mutate(), refreshSchedules(), refreshContracts()]);
      setEditing(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.people.toasts.saved") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleRemove = async (person: THrEmploymentProfile) => {
    setIsBusy(true);
    try {
      await hrService.removeEmployee(person.id);
      await Promise.all([mutate(), refreshCandidates()]);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.people.toasts.removed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  if (isLoading)
    return (
      <Loader className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-6 py-6">
        <Loader.Item height="48px" />
        <Loader.Item height="280px" />
      </Loader>
    );

  if (error)
    return (
      <div className="mx-auto w-full max-w-6xl px-6 py-6">
        <div className="border-custom-border-200 bg-custom-background-90 rounded-md border px-4 py-6">
          <p className="text-custom-text-200 text-sm font-medium">{t("hr.team_time.not_permitted")}</p>
          <p className="text-custom-text-300 text-sm mt-1">{t("hr.people.not_permitted_detail")}</p>
        </div>
      </div>
    );

  const rows = people ?? [];
  const scheduleFor = (profileId: string) => (schedules ?? []).find((row) => row.profile === profileId) ?? null;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-6 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-custom-text-100 text-lg font-semibold">{t("hr.people.title")}</h1>
          <p className="text-custom-text-300 text-sm">{t("hr.people.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Link to={`/${workspaceSlug}/team-time`}>
            <Button variant="secondary" size="sm" prependIcon={<CalendarClock className="size-4" />}>
              {t("hr.people.back_to_month")}
            </Button>
          </Link>
          <Button variant="primary" size="sm" prependIcon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
            {t("hr.people.add")}
          </Button>
        </div>
      </div>

      <HrAddPersonModal
        isOpen={adding}
        candidates={candidates ?? []}
        isBusy={isBusy}
        onClose={() => setAdding(false)}
        onAdd={(memberId, hireDate) => void handleAdd(memberId, hireDate)}
      />

      <HrPersonModal
        isOpen={editing !== null}
        person={editing}
        contract={pickCurrent(contracts ?? [])}
        schedule={editing ? scheduleFor(editing.id) : null}
        isBusy={isBusy}
        onClose={() => setEditing(null)}
        onSave={(draft) => void handleSave(draft)}
      />

      {rows.length === 0 ? (
        <div className="border-custom-border-200 bg-custom-background-90 text-custom-text-300 text-sm rounded-md border px-4 py-8 text-center">
          {t("hr.people.nobody_yet")}
        </div>
      ) : (
        <div className="border-custom-border-200 overflow-x-auto rounded-md border">
          <table className="text-sm w-full min-w-[46rem]">
            <thead className="bg-custom-background-90 text-custom-text-400 text-xs tracking-wide uppercase">
              <tr>
                <th className="px-4 py-2 text-left font-medium">{t("hr.people.column_person")}</th>
                <th className="px-4 py-2 text-left font-medium">{t("hr.people.column_since")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("hr.people.column_week")}</th>
                <th className="px-4 py-2 text-left font-medium">{t("hr.people.column_role")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("hr.people.column_action")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((person) => {
                const schedule = scheduleFor(person.id);
                return (
                  <tr
                    key={person.id}
                    className={cn(
                      "border-custom-border-200 hover:bg-custom-background-90/60 border-t",
                      !person.is_active && "text-custom-text-400"
                    )}
                  >
                    <td className="px-4 py-2">
                      <span className="text-custom-text-100 block">
                        {person.member_display_name || person.member_email}
                      </span>
                      <span className="text-custom-text-400 text-xs">{person.member_email}</span>
                    </td>
                    <td className="text-custom-text-300 px-4 py-2">{person.hire_date ?? "—"}</td>
                    <td className="text-custom-text-200 px-4 py-2 text-right tabular-nums">
                      {schedule ? formatMinutes(schedule.weekly_minutes) : "—"}
                    </td>
                    <td className="px-4 py-2">
                      {person.is_hr_manager ? (
                        <span className="bg-custom-primary-100/10 text-custom-primary-100 text-xs rounded px-2 py-0.5 font-medium">
                          {t("hr.people.manager")}
                        </span>
                      ) : (
                        <span className="text-custom-text-400 text-xs">{t("hr.people.employee")}</span>
                      )}
                      {!person.is_active ? (
                        <span className="text-custom-text-400 text-xs ml-2">{t("hr.people.left")}</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="link" size="sm" onClick={() => setEditing(person)}>
                          {t("hr.people.edit")}
                        </Button>
                        {person.is_active ? (
                          <Button
                            variant="link"
                            size="sm"
                            prependIcon={<UserMinus className="size-3.5" />}
                            onClick={() => void handleRemove(person)}
                          >
                            {t("hr.people.remove")}
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-custom-text-400 text-xs">{t("hr.people.footnote")}</p>
    </div>
  );
});

/** The terms in force now: the latest that has started. */
function pickCurrent(contracts: THrContract[]): THrContract | null {
  return contracts.reduce<THrContract | null>(
    (latest, row) => (latest === null || row.valid_from > latest.valid_from ? row : latest),
    null
  );
}
