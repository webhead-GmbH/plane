/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Check, ChevronLeft, ChevronRight, Pencil, Plus, Settings2, Trash2, X } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { setToast, TOAST_TYPE } from "@plane/propel/toast";
import { AlertModalCore, Loader } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import {
  EHrAbsenceState,
  EHrGranularity,
  HrService,
  type THrAbsence,
  type THrAbsenceType,
  type THrEmploymentProfile,
} from "@/services/hr.service";
// local imports
import { HrAbsenceModal, type TAbsenceDraft } from "./absence-modal";
import { HrAbsenceTypesModal } from "./absence-types-modal";
import { HrReasonModal } from "./reason-modal";
import { HrRowAction } from "./row-action";
import {
  formatDayLabel,
  formatMinutes,
  formatMonthLabel,
  localName,
  nextMonth,
  previousMonth,
  refusalMessage,
} from "./utils";

const hrService = new HrService();

const STATE_KEY: Record<number, string> = {
  [EHrAbsenceState.DRAFT]: "draft",
  [EHrAbsenceState.REQUESTED]: "requested",
  [EHrAbsenceState.APPROVED]: "approved",
  [EHrAbsenceState.REJECTED]: "rejected",
  [EHrAbsenceState.CANCELLED]: "cancelled",
};

const STATE_TONE: Record<number, string> = {
  [EHrAbsenceState.DRAFT]: "bg-layer-2 text-tertiary",
  [EHrAbsenceState.REQUESTED]: "bg-warning-subtle text-warning-primary",
  [EHrAbsenceState.APPROVED]: "bg-success-subtle text-success-primary",
  [EHrAbsenceState.REJECTED]: "bg-danger-subtle text-danger-primary",
  [EHrAbsenceState.CANCELLED]: "bg-layer-2 text-tertiary line-through",
};

/**
 * First and last day of a month, as the window the list is asked for.
 *
 * Written out rather than taken from a Date, because `new Date(year, month, 0)`
 * is local midnight and `toISOString` reads it back in UTC — so anywhere east of
 * Greenwich the last day of the month came out as the second to last, and an
 * absence on the 31st was simply missing from the list.
 */
const lastDayOfMonth = (year: number, month: number) => new Date(year, month, 0).getDate();

const monthWindow = (year: number, month: number) => ({
  from: `${year}-${String(month).padStart(2, "0")}-01`,
  to: `${year}-${String(month).padStart(2, "0")}-${String(lastDayOfMonth(year, month)).padStart(2, "0")}`,
});

/**
 * Whose absence this is, by the name the rest of the product knows them by.
 *
 * A dash while the roster is still on its way, so a row is never blank.
 */
const nameOf = (people: THrEmploymentProfile[], profileId: string) =>
  people.find((person: THrEmploymentProfile) => person.id === profileId)?.member_display_name ?? "—";

/**
 * Who is away, and when.
 *
 * A month at a time, because that is the unit everything else here closes in and
 * an absence is only interesting next to the month it changes. The window catches
 * an absence that merely touches the month, so a holiday running over a month end
 * appears in both — dropping it from the second would hide days that are missing
 * from that month's target.
 */
export const HrAbsencesRoot = observer(function HrAbsencesRoot() {
  const { t, currentLocale } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [personFilter, setPersonFilter] = useState("");
  const [removing, setRemoving] = useState<THrAbsence | null>(null);
  const [refusing, setRefusing] = useState<THrAbsence | null>(null);
  const [recording, setRecording] = useState(false);
  const [editing, setEditing] = useState<THrAbsence | null>(null);
  const [managingTypes, setManagingTypes] = useState(false);
  const [isBusy, setIsBusy] = useState(false);

  const { from, to } = monthWindow(year, month);

  const {
    data: absences,
    isLoading,
    error,
    mutate,
  } = useSWR(`HR_ABSENCES_${from}_${to}_${personFilter}`, () =>
    hrService.absences(from, to, personFilter || undefined)
  );
  const { data: people } = useSWR("HR_EMPLOYEES", () => hrService.employees());
  const { data: types, mutate: refreshTypes } = useSWR("HR_ABSENCE_TYPES", () => hrService.absenceTypes());
  // Deciding on absences and editing the reasons belong to whoever looks after
  // the team. Showing those controls to everybody meant an ordinary employee
  // could press them and get an English refusal from the server.
  const { data: me } = useSWR("HR_ME_ROLE", () => hrService.me());
  const isManager = Boolean(me?.is_hr_manager);

  const complain = (failure: unknown) =>
    setToast({
      type: TOAST_TYPE.ERROR,
      title: t("hr.absences.toasts.refused"),
      message: refusalMessage(failure, t, currentLocale) ?? t("hr.absences.toasts.try_again"),
    });

  const step = (move: (year: number, month: number) => [number, number]) => {
    const [nextYear, nextMonthNumber] = move(year, month);
    setYear(nextYear);
    setMonth(nextMonthNumber);
  };

  const handleSave = async (draft: TAbsenceDraft) => {
    setIsBusy(true);
    try {
      if (editing) await hrService.updateAbsence(editing.id, { ...draft });
      else await hrService.createAbsence({ ...draft });
      await mutate();
      setRecording(false);
      setEditing(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.absences.toasts.saved") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleDecide = async (absence: THrAbsence, decision: "approve" | "cancel", reason?: string) => {
    setIsBusy(true);
    try {
      await hrService.decideAbsence(absence.id, decision, reason);
      await mutate();
      // Agreeing charges somebody's leave and cannot be taken back from here, and
      // a pill quietly changing colour is not an answer to a click on a small icon.
      if (decision === "approve") setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.absences.state.approved") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const handleRefuse = async (absence: THrAbsence, reason: string) => {
    setIsBusy(true);
    try {
      await hrService.decideAbsence(absence.id, "reject", reason);
      await mutate();
      setRefusing(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.absences.state.rejected") });
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
      await hrService.removeAbsence(removing.id);
      await mutate();
      setRemoving(null);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("hr.absences.toasts.removed") });
    } catch (failure) {
      complain(failure);
    } finally {
      setIsBusy(false);
    }
  };

  const notAllowed = (error as { status?: number } | undefined)?.status === 403;
  const hasData = Boolean(absences);

  // Only when there is nothing to show: a revalidation that failed while the
  // screen already holds good data must not replace it with an error.
  if (error && (notAllowed || !hasData))
    return <AbsencesUnavailable notAllowed={notAllowed} onRetry={() => void mutate()} />;

  const rows = absences ?? [];
  const roster = people ?? [];
  const absenceTypes = types ?? [];

  const monthLabel = formatMonthLabel(from, currentLocale);

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-13 text-tertiary">{t("hr.absences.subtitle")}</p>
        <div className="flex items-center gap-2">
          {isManager ? (
            <Button
              variant="secondary"
              size="lg"
              prependIcon={<Settings2 className="size-4" />}
              onClick={() => setManagingTypes(true)}
            >
              {t("hr.absences.manage_types")}
            </Button>
          ) : null}
          <Button
            variant="primary"
            size="lg"
            prependIcon={<Plus />}
            onClick={() => {
              setEditing(null);
              setRecording(true);
            }}
          >
            {isManager ? t("hr.absences.record") : t("hr.absences.request")}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-md border border-subtle px-1 py-0.5">
          <button
            type="button"
            className="p-1 text-tertiary hover:text-primary"
            aria-label={t("hr.absences.previous_month")}
            onClick={() => step(previousMonth)}
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="min-w-[9rem] text-center text-13 font-medium text-secondary">{monthLabel}</span>
          <button
            type="button"
            className="p-1 text-tertiary hover:text-primary"
            aria-label={t("hr.absences.next_month")}
            onClick={() => step(nextMonth)}
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <select
          aria-label={t("hr.absences.filter_person")}
          className="rounded-md border border-subtle bg-layer-1 px-3 py-1.5 text-13 text-secondary"
          value={personFilter}
          onChange={(event) => setPersonFilter(event.target.value)}
        >
          <option value="">{t("hr.absences.everyone")}</option>
          {roster.map((person) => (
            <option key={person.id} value={person.id}>
              {person.member_display_name}
            </option>
          ))}
        </select>
      </div>

      <AbsenceDialogs
        recording={recording}
        editing={editing}
        refusing={refusing}
        removing={removing}
        managingTypes={managingTypes}
        people={roster}
        types={absenceTypes}
        isBusy={isBusy}
        onCloseAbsence={() => {
          setRecording(false);
          setEditing(null);
        }}
        onSave={(draft) => void handleSave(draft)}
        onCloseRefusal={() => setRefusing(null)}
        onRefuse={handleRefuse}
        onCloseRemoval={() => setRemoving(null)}
        onRemove={() => void handleRemove()}
        onCloseTypes={() => setManagingTypes(false)}
        onTypesChanged={() => refreshTypes()}
      />

      <AbsencesList
        isLoading={isLoading}
        rows={rows}
        people={roster}
        isManager={isManager}
        isBusy={isBusy}
        onApprove={(absence) => void handleDecide(absence, "approve")}
        onReject={setRefusing}
        onEdit={setEditing}
        onRemove={setRemoving}
      />
    </div>
  );
});

type TUnavailableProps = {
  /** The list was refused rather than broken: this screen is not theirs to see. */
  notAllowed: boolean;
  onRetry: () => void;
};

const AbsencesUnavailable = ({ notAllowed, onRetry }: TUnavailableProps) => {
  const { t } = useTranslation();

  return (
    <div className="w-full">
      <EmptyStateCompact
        title={notAllowed ? t("hr.team_time.not_permitted") : t("hr.shared.load_failed")}
        description={notAllowed ? t("hr.absences.not_permitted_detail") : t("hr.shared.load_failed_detail")}
        assetKey={notAllowed ? "members" : "unknown"}
        assetClassName="size-20"
        rootClassName="py-16"
        actions={notAllowed ? undefined : [{ label: t("hr.shared.retry"), variant: "secondary", onClick: onRetry }]}
      />
    </div>
  );
};

type TDialogsProps = {
  recording: boolean;
  /** The absence being changed, or null when a new one is being recorded. */
  editing: THrAbsence | null;
  refusing: THrAbsence | null;
  removing: THrAbsence | null;
  managingTypes: boolean;
  people: THrEmploymentProfile[];
  types: THrAbsenceType[];
  isBusy: boolean;
  onCloseAbsence: () => void;
  onSave: (draft: TAbsenceDraft) => void;
  onCloseRefusal: () => void;
  onRefuse: (absence: THrAbsence, reason: string) => Promise<void>;
  onCloseRemoval: () => void;
  onRemove: () => void;
  onCloseTypes: () => void;
  onTypesChanged: () => Promise<unknown>;
};

const AbsenceDialogs = ({
  recording,
  editing,
  refusing,
  removing,
  managingTypes,
  people,
  types,
  isBusy,
  onCloseAbsence,
  onSave,
  onCloseRefusal,
  onRefuse,
  onCloseRemoval,
  onRemove,
  onCloseTypes,
  onTypesChanged,
}: TDialogsProps) => {
  const { t } = useTranslation();

  return (
    <>
      <HrAbsenceModal
        isOpen={recording || editing !== null}
        absence={editing}
        people={people}
        types={types}
        isBusy={isBusy}
        onClose={onCloseAbsence}
        onSave={onSave}
      />

      {/* Refusing has to say why: the endpoint requires it, and the person whose
          leave it was is going to ask. */}
      <HrReasonModal
        key={refusing?.id ?? "none"}
        isOpen={refusing !== null}
        title={t("hr.absences.refuse_title", { person: refusing ? nameOf(people, refusing.profile) : "" })}
        body={t("hr.absences.refuse_body")}
        label={t("hr.absences.refuse_label")}
        placeholder={t("hr.absences.refuse_placeholder")}
        confirmLabel={t("hr.absences.reject")}
        cancelLabel={t("hr.absences.refuse_cancel")}
        isBusy={isBusy}
        onClose={onCloseRefusal}
        onConfirm={async (reason) => {
          if (!refusing) return;
          await onRefuse(refusing, reason);
        }}
      />

      <AlertModalCore
        isOpen={removing !== null}
        handleClose={onCloseRemoval}
        handleSubmit={onRemove}
        isSubmitting={isBusy}
        variant="danger"
        title={t("hr.absences.confirm_remove_title")}
        content={t("hr.absences.confirm_remove_body", {
          person: removing ? nameOf(people, removing.profile) : "",
          duration: removing ? formatMinutes(removing.total_minutes) : "",
        })}
        primaryButtonText={{ default: t("hr.absences.delete"), loading: t("hr.absences.removing") }}
        secondaryButtonText={t("common.cancel")}
      />

      <HrAbsenceTypesModal isOpen={managingTypes} types={types} onClose={onCloseTypes} onChanged={onTypesChanged} />
    </>
  );
};

type TRowHandlers = {
  isManager: boolean;
  isBusy: boolean;
  onApprove: (absence: THrAbsence) => void;
  onReject: (absence: THrAbsence) => void;
  onEdit: (absence: THrAbsence) => void;
  onRemove: (absence: THrAbsence) => void;
};

type TListProps = TRowHandlers & {
  isLoading: boolean;
  rows: THrAbsence[];
  people: THrEmploymentProfile[];
};

const AbsencesList = ({ isLoading, rows, people, ...handlers }: TListProps) => {
  const { t } = useTranslation();

  if (isLoading)
    return (
      <Loader className="flex flex-col gap-3">
        <Loader.Item height="48px" />
        <Loader.Item height="220px" />
      </Loader>
    );

  if (rows.length === 0)
    return (
      <EmptyStateCompact
        title={t("hr.absences.none_this_month")}
        assetKey="note"
        assetClassName="size-20"
        rootClassName="py-16"
      />
    );

  return (
    <div className="overflow-x-auto rounded-md border border-subtle">
      <table className="w-full min-w-[52rem] text-13">
        <thead className="border-b border-subtle text-13 text-placeholder">
          <tr>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.absences.column_person")}</th>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.absences.column_reason")}</th>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.absences.column_when")}</th>
            <th className="px-4 py-2.5 text-right font-medium">{t("hr.absences.column_away")}</th>
            <th className="px-4 py-2.5 text-left font-medium">{t("hr.absences.column_state")}</th>
            <th className="px-4 py-2.5 text-right font-medium">{t("hr.absences.column_action")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((absence) => (
            <AbsenceRow key={absence.id} absence={absence} people={people} {...handlers} />
          ))}
        </tbody>
      </table>
    </div>
  );
};

type TRowProps = TRowHandlers & {
  absence: THrAbsence;
  people: THrEmploymentProfile[];
};

const AbsenceRow = ({ absence, people, ...handlers }: TRowProps) => {
  const { t, currentLocale } = useTranslation();
  const person = nameOf(people, absence.profile);
  // A closed month is nobody's to change from here, and an absence that was
  // cancelled or refused has nothing left worth editing.
  const locked = Boolean(absence.locked_period);
  const settled = absence.state === EHrAbsenceState.CANCELLED || absence.state === EHrAbsenceState.REJECTED;

  return (
    <tr className="border-t border-subtle hover:bg-layer-1/60">
      <td className="px-4 py-2 text-primary">{person}</td>
      <td className="px-4 py-2 text-secondary">
        {localName({ name_de: absence.absence_type_name, name_en: absence.absence_type_name_en }, currentLocale) ||
          absence.absence_type_code}
        {absence.reason && <span className="ml-2 text-13 text-tertiary">{absence.reason}</span>}
      </td>
      <td className="px-4 py-2 text-secondary">
        <AbsenceWhen absence={absence} />
      </td>
      <td className="px-4 py-2 text-right text-secondary tabular-nums">{formatMinutes(absence.total_minutes)}</td>
      <td className="px-4 py-2">
        <span className={cn("rounded px-1.5 py-0.5 text-13 font-medium", STATE_TONE[absence.state])}>
          {t(`hr.absences.state.${STATE_KEY[absence.state]}`)}
        </span>
        {locked && <span className="ml-2 text-13 text-tertiary">{t("hr.absences.month_locked")}</span>}
      </td>
      <td className="px-4 py-2 text-right">
        <AbsenceActions absence={absence} person={person} locked={locked} settled={settled} {...handlers} />
      </td>
    </tr>
  );
};

/**
 * The days somebody is away, and how much of each of them.
 *
 * One date rather than a range of one, and the fraction only where it is not a
 * whole day — a column that said "full day" on every line said nothing.
 */
const AbsenceWhen = ({ absence }: { absence: THrAbsence }) => {
  const { t, currentLocale } = useTranslation();
  const isOneDay = absence.start_date === absence.end_date;

  return (
    <>
      {isOneDay
        ? formatDayLabel(absence.start_date, currentLocale)
        : `${formatDayLabel(absence.start_date, currentLocale)} – ${formatDayLabel(absence.end_date, currentLocale)}`}
      {absence.granularity !== EHrGranularity.FULL_DAY && (
        <span className="ml-2 text-13 text-tertiary">
          {absence.granularity === EHrGranularity.HALF_DAY
            ? t(isOneDay ? "hr.absences.granularity.half_day_single" : "hr.absences.granularity.half_day")
            : t("hr.absences.granularity.hours")}
        </span>
      )}
    </>
  );
};

type TActionsProps = TRowHandlers & {
  absence: THrAbsence;
  /** Named in every label, so a screen reader can tell the rows apart. */
  person: string;
  locked: boolean;
  settled: boolean;
};

const AbsenceActions = ({
  absence,
  person,
  locked,
  settled,
  isManager,
  isBusy,
  onApprove,
  onReject,
  onEdit,
  onRemove,
}: TActionsProps) => {
  const { t } = useTranslation();

  return (
    <div className="flex items-center justify-end gap-0.5">
      {isManager && absence.state === EHrAbsenceState.REQUESTED && !locked && (
        <>
          <HrRowAction
            icon={<Check className="size-4" />}
            label={t("hr.absences.approve")}
            subject={person}
            disabled={isBusy}
            onClick={() => onApprove(absence)}
          />
          <HrRowAction
            icon={<X className="size-4" />}
            label={t("hr.absences.reject")}
            subject={person}
            danger
            disabled={isBusy}
            onClick={() => onReject(absence)}
          />
        </>
      )}
      {/* An absence that has already been agreed is only whoever looks after the
          team's to change. Offering anybody else the pencil opens a dialog the
          server then refuses, in English, with the dialog left standing open. */}
      {!locked && !settled && (isManager || absence.state !== EHrAbsenceState.APPROVED) && (
        <HrRowAction
          icon={<Pencil className="size-4" />}
          label={t("common.edit")}
          subject={person}
          disabled={isBusy}
          onClick={() => onEdit(absence)}
        />
      )}
      {isManager && !locked && (
        <HrRowAction
          icon={<Trash2 className="size-4" />}
          label={t("hr.absences.delete")}
          subject={person}
          danger
          disabled={isBusy}
          onClick={() => onRemove(absence)}
        />
      )}
    </div>
  );
};
