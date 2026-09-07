/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { BadgeEuro, MoreHorizontal, Palmtree, Pencil, Plus, Scale, UserMinus, UserPlus } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { AlertModalCore, CustomMenu, Loader } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import { HrService, type THrContract, type THrEmploymentProfile } from "@/services/hr.service";
// local imports
import { HrAddPersonModal } from "./add-person-modal";
import { HrRowAction } from "./row-action";
import { HrOpeningBalanceModal } from "./opening-balance-modal";
import { HrLeaveModal } from "./leave-modal";
import { HrRateCardModal } from "./rate-card-modal";
import { HrPersonModal, type TPersonDraft } from "./person-modal";
import { formatDayWithYear, formatMinutes, refusalMessage } from "./utils";

const hrService = new HrService();

/**
 * The people the company employs, and the terms each of them works under.
 *
 * Reached from the team's month rather than from workspace settings. Looking
 * after the team is a property of the person here, deliberately not the same
 * thing as administering a workspace — filing this under workspace settings
 * would have let an administrator in and kept the actual manager out.
 */
export const HrPeopleRoot = observer(function HrPeopleRoot() {
  const { t, currentLocale } = useTranslation();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<THrEmploymentProfile | null>(null);
  const [opening, setOpening] = useState<THrEmploymentProfile | null>(null);
  const [rating, setRating] = useState<THrEmploymentProfile | null>(null);
  const [leaving, setLeaving] = useState<THrEmploymentProfile | null>(null);
  const [removing, setRemoving] = useState<THrEmploymentProfile | null>(null);
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
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.people.toasts.try_again"),
    });

  const handleAdd = async (memberId: string, hireDate: string) => {
    setIsBusy(true);
    try {
      const created = await hrService.createEmployee({
        member: memberId,
        hire_date: hireDate,
        timezone: "Europe/Vienna",
      });
      await Promise.all([mutate(), refreshCandidates()]);
      setAdding(false);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.people.toasts.added") });
      // Straight on to their hours and terms. A person with no schedule of their
      // own has months computed against nothing, and the mistake only surfaces
      // weeks later as a balance nobody can explain.
      if (created) setEditing(created);
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

  /**
   * Put somebody back on the books.
   *
   * Marking a person as having left is not a deletion — their closed months have
   * to stay readable — but it left them stranded: the list showed them greyed
   * out with no action, and the list of people who could be given a record
   * excludes anyone who already has one. Somebody coming back after a break, or
   * marked as left by mistake, could not be reached from either screen.
   *
   * The leaving date goes with it. A record that says somebody is employed and
   * also says the day they left is a contradiction, and it is the date the month
   * figures read.
   */
  const handleReturn = async (person: THrEmploymentProfile) => {
    setIsBusy(true);
    try {
      await hrService.updateEmployee(person.id, { is_active: true, exit_date: null });
      await Promise.all([mutate(), refreshCandidates()]);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.people.toasts.brought_back") });
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
      await hrService.removeEmployee(removing.id);
      await Promise.all([mutate(), refreshCandidates()]);
      setRemoving(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.people.toasts.removed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  if (isLoading)
    return (
      <Loader className="flex w-full flex-col gap-7">
        <Loader.Item height="48px" />
        <Loader.Item height="280px" />
      </Loader>
    );

  const notAllowed = (error as { status?: number } | undefined)?.status === 403;
  const hasData = Boolean(people);

  // Only when there is nothing to show: a revalidation that failed while the
  // screen already holds good data must not replace it with an error.
  if (error && (notAllowed || !hasData))
    return (
      <div className="w-full">
        <EmptyStateCompact
          title={notAllowed ? t("hr.team_time.not_permitted") : t("hr.shared.load_failed")}
          description={notAllowed ? t("hr.people.not_permitted_detail") : t("hr.shared.load_failed_detail")}
          assetKey={notAllowed ? "members" : "unknown"}
          assetClassName="size-20"
          rootClassName="py-16"
          actions={
            notAllowed
              ? undefined
              : [{ label: t("hr.shared.retry"), variant: "secondary", onClick: () => void mutate() }]
          }
        />
      </div>
    );

  const rows = people ?? [];
  const scheduleFor = (profileId: string) => (schedules ?? []).find((row) => row.profile === profileId) ?? null;

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-13 text-tertiary">{t("hr.people.subtitle")}</p>
        <div className="flex items-center gap-2">
          <Button variant="primary" size="lg" prependIcon={<Plus />} onClick={() => setAdding(true)}>
            {t("hr.people.add")}
          </Button>
        </div>
      </div>

      <HrAddPersonModal
        key={adding ? "open" : "closed"}
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

      <HrOpeningBalanceModal
        key={opening?.id ?? "none"}
        person={opening}
        isOwn={false}
        canRecord
        onClose={() => setOpening(null)}
      />

      <HrRateCardModal key={rating?.id ?? "none"} person={rating} onClose={() => setRating(null)} />

      <HrLeaveModal
        key={leaving?.id ?? "none"}
        person={leaving}
        schedule={leaving ? scheduleFor(leaving.id) : null}
        onClose={() => setLeaving(null)}
      />

      {/* Marking somebody as having left is the one action here that changes what
          every future month says about them, and it used to happen on one click
          of the fifth identical link in a row. */}
      <AlertModalCore
        isOpen={removing !== null}
        handleClose={() => setRemoving(null)}
        handleSubmit={() => void handleRemove()}
        isSubmitting={isBusy}
        variant="danger"
        title={t("hr.people.confirm_remove_title")}
        content={`${t("hr.people.confirm_remove_body", {
          person: removing?.member_display_name || removing?.member_email || "",
        })} ${t("hr.people.confirm_remove_permanent")}`}
        primaryButtonText={{
          default: t("hr.people.remove"),
          loading: t("hr.people.removing"),
        }}
      />

      {rows.length === 0 ? (
        <EmptyStateCompact
          title={t("hr.people.nobody_yet")}
          assetKey="work-item"
          assetClassName="size-20"
          rootClassName="py-16"
        />
      ) : (
        <div className="overflow-x-auto rounded-md border border-subtle">
          <table className="w-full min-w-[46rem] text-13">
            <thead className="border-b border-subtle text-13 text-placeholder">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">{t("hr.people.column_person")}</th>
                <th className="px-4 py-2.5 text-left font-medium">{t("hr.people.column_since")}</th>
                <th className="px-4 py-2.5 text-right font-medium">{t("hr.people.column_week")}</th>
                <th className="px-4 py-2.5 text-left font-medium">{t("hr.people.column_role")}</th>
                <th className="px-4 py-2.5 text-right font-medium">{t("hr.people.column_action")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((person) => {
                const schedule = scheduleFor(person.id);
                return (
                  <tr
                    key={person.id}
                    className={cn("border-t border-subtle hover:bg-layer-1/60", !person.is_active && "text-tertiary")}
                  >
                    <td className="px-4 py-2">
                      <span className="block text-primary">{person.member_display_name || person.member_email}</span>
                      <span className="text-13 text-tertiary">{person.member_email}</span>
                      {/*
                        Said here rather than only inside the edit dialog, because
                        nobody opens the dialog for somebody they have no reason to
                        suspect — and a person whose hours are not reaching the CRM
                        looks exactly like everybody else until payroll is short.
                      */}
                      {person.is_active && person.crm_link !== "set" ? (
                        <span
                          className="block text-13 text-tertiary"
                          title={t(`hr.people.crm_link.${person.crm_link}`)}
                        >
                          {person.crm_link === "none" ? t("hr.people.crm_missing") : t("hr.people.crm_guessed")}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-2 text-tertiary">
                      {/* Not the raw `2024-03-01` the API sends: this column is
                          read alongside names and roles, and an ISO date in the
                          middle of them reads as a serial number. */}
                      {person.hire_date ? formatDayWithYear(person.hire_date, currentLocale) : "—"}
                    </td>
                    <td className="px-4 py-2 text-right text-secondary tabular-nums">
                      {schedule ? (
                        formatMinutes(schedule.weekly_minutes)
                      ) : (
                        <span className="text-warning-primary">{t("hr.people.no_hours_yet")}</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {person.is_hr_manager ? (
                        <span className="rounded bg-accent-primary/10 px-2 py-0.5 text-13 font-medium text-accent-primary">
                          {t("hr.people.manager")}
                        </span>
                      ) : (
                        <span className="text-13 text-tertiary">{t("hr.people.employee")}</span>
                      )}
                      {!person.is_active ? (
                        <span className="ml-2 text-13 text-tertiary">{t("hr.people.left")}</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {/* Icons rather than five underlined words per row: the words
                          were a wall of identical blue that had to be read to be
                          told apart, and the last of them ends somebody's
                          employment. Each carries its own name for a screen reader
                          and a tooltip for everyone else, and the destructive one
                          is set apart by a rule and by colour rather than sitting
                          fifth in a row of equals. */}
                      <div className="flex items-center justify-end gap-0.5">
                        <HrRowAction
                          icon={<Pencil className="size-4" />}
                          label={t("hr.people.edit")}
                          subject={person.member_display_name || person.member_email || ""}
                          onClick={() => setEditing(person)}
                        />
                        <CustomMenu
                          customButton={
                            <span className="grid size-7 place-items-center rounded-md text-tertiary transition-colors hover:bg-layer-2 hover:text-primary">
                              <MoreHorizontal className="size-4" />
                            </span>
                          }
                          placement="bottom-end"
                          closeOnSelect
                        >
                          <CustomMenu.MenuItem onClick={() => setOpening(person)} className="flex items-center gap-2">
                            <Scale className="size-3 shrink-0" />
                            {t("hr.people.opening")}
                          </CustomMenu.MenuItem>
                          <CustomMenu.MenuItem onClick={() => setRating(person)} className="flex items-center gap-2">
                            <BadgeEuro className="size-3 shrink-0" />
                            {t("hr.people.rates")}
                          </CustomMenu.MenuItem>
                          <CustomMenu.MenuItem onClick={() => setLeaving(person)} className="flex items-center gap-2">
                            <Palmtree className="size-3 shrink-0" />
                            {t("hr.people.leave")}
                          </CustomMenu.MenuItem>
                          {person.is_active ? (
                            <CustomMenu.MenuItem
                              onClick={() => setRemoving(person)}
                              className="flex items-center gap-2 text-danger-primary"
                            >
                              <UserMinus className="size-3 shrink-0" />
                              {t("hr.people.remove")}
                            </CustomMenu.MenuItem>
                          ) : (
                            <CustomMenu.MenuItem
                              onClick={() => void handleReturn(person)}
                              className="flex items-center gap-2"
                            >
                              <UserPlus className="size-3 shrink-0" />
                              {t("hr.people.bring_back")}
                            </CustomMenu.MenuItem>
                          )}
                        </CustomMenu>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-13 text-tertiary">{t("hr.people.footnote")}</p>
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
