# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Bringing in hours and absences recorded before this module existed.

Nothing is written until somebody has seen what would be written. A file is
parsed, every row is checked, and the result is shown back with a verdict on each
one; only then does committing produce records. Each of those carries the batch
that made it, so undoing is exact rather than approximate.

The important constraint is not in this file but is the reason for its shape:
imported hours are never written as work item timers. A timer is mirrored to the
customer billing system the moment it is saved, so importing three years of
history that way would replay all of it into invoicing. They become entries that
have no work item, which the mirror cannot see.
"""

# Python imports
import hashlib
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Django imports
from django.db import transaction
from django.utils import timezone

# Module imports
from plane.hr.models import (
    HrAbsence,
    HrAbsenceType,
    HrEmploymentProfile,
    HrImportBatch,
    HrOpeningBalance,
    HrPeriod,
    HrTimeEntry,
)
from plane.hr.services.refusal import Refused
from plane.hr.services.settled import settled_month_across
from plane.utils.porters.formatters import CSVFormatter, XLSXFormatter

# What a row may be: a good one, one that cannot be used, or one that is already
# here and would otherwise be counted twice.
OK = "ok"
ERROR = "error"
SKIP = "skip"


def checksum(content):
    """A fingerprint of the uploaded bytes, so the same file is not applied twice."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def parse(content, file_format):
    """Rows out of a file, without judging them yet."""
    if file_format == "csv":
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
        return CSVFormatter().decode(text)
    if file_format in ("xlsx", "xls"):
        return XLSXFormatter().decode(content)
    raise Refused("Only CSV and XLSX files can be read.")


def _as_date(value):
    if value in (None, ""):
        return None
    if hasattr(value, "date") and not isinstance(value, str):
        return value.date()
    if hasattr(value, "year") and not isinstance(value, str):
        return value
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value).strip(), pattern).date()
        except ValueError:
            continue
    return None


# Which column a length of time came from decides what a bare number in it means.
# The same "7.7" is seven and a half hours under one heading and seven minutes
# under another, and nothing in the value itself says which.
_MINUTE_COLUMNS = ("minutes", "minuten")
_HOUR_COLUMNS = ("hours", "stunden", "std")


def _length_column(row):
    """The cell holding a length of time, and the unit its heading implies.

    Returns ``(value, unit)`` where unit is "minutes" or "hours". A heading
    naming minutes wins over one naming hours, so a sheet carrying both is read
    the precise way rather than the rounded one.
    """
    for name in _MINUTE_COLUMNS:
        if row.get(name) not in (None, ""):
            return row.get(name), "minutes"
    for name in _HOUR_COLUMNS:
        if row.get(name) not in (None, ""):
            return row.get(name), "hours"
    return None, "minutes"


def _as_minutes(value, unit="minutes"):
    """Minutes from a cell holding ``7:42``, or a number in the given unit.

    ``7:42`` says what it is and is read the same way under either heading.
    A bare number cannot say, so the caller supplies the unit from the column
    heading — reading an hours column as minutes would divide every imported
    month by sixty, and nothing downstream would notice.
    """
    if value in (None, ""):
        return None
    raw = str(value).strip().replace(",", ".")
    if ":" in raw:
        try:
            hours, minutes = raw.split(":", 1)
            sign = -1 if hours.strip().startswith("-") else 1
            return sign * (abs(int(hours)) * 60 + int(minutes))
        except (TypeError, ValueError):
            return None
    try:
        amount = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if unit == "hours":
        # Rounded, not truncated: 7.7 hours is 462 minutes, and dropping the
        # remainder would quietly shorten most rows in a decimal-hours sheet.
        return int((amount * 60).to_integral_value(rounding=ROUND_HALF_UP))
    return int(amount)


class RowResult:
    """One row of an upload, and what is to be done with it.

    ``reason`` is a stable name for why, and ``detail`` the handful of values that
    name mentions. The English sentence is kept alongside them: it is what an
    older preview already stored, and what anybody reading the batch straight out
    of the database sees. Sending only the sentence meant the one screen in this
    module a person meets a wall on — an upload that was refused — was the one
    screen that could not be in their language.
    """

    __slots__ = ("index", "verdict", "message", "data", "reason", "detail")

    def __init__(self, index, verdict, message="", data=None, reason="", detail=None):
        self.index = index
        self.verdict = verdict
        self.message = message
        self.data = data or {}
        self.reason = reason
        self.detail = detail or {}

    def as_dict(self):
        return {
            "row": self.index,
            "verdict": self.verdict,
            "reason": self.reason,
            "detail": self.detail,
            "message": self.message,
            "data": {key: str(value) for key, value in self.data.items()},
        }


class _Loader:
    """Shared checking for every kind of import."""

    def __init__(self, workspace):
        self.workspace = workspace
        self._profiles = {}

    def profile_for(self, email):
        """The person a row is about, matched on the address they log in with."""
        if not email:
            return None
        key = str(email).strip().lower()
        if key not in self._profiles:
            self._profiles[key] = (
                HrEmploymentProfile.objects.filter(workspace=self.workspace, member__email__iexact=key)
                .select_related("member")
                .first()
            )
        return self._profiles[key]

    def month_is_closed(self, profile, day, until=None):
        """Whether any month this touches has stopped being rebuilt.

        A range rather than a day, because an absence has two ends and can lie
        across a month boundary. Asking only about the day it starts on let a week
        beginning on the 28th of an open January be written straight through into
        a February that was already closed — where it would reduce a target nobody
        will recompute, so the closed figure and the records behind it disagree
        and neither says which is right.

        Handed in and approved count as closed here. Neither is rebuilt again, so
        an import into one is just as invisible as an import into a locked month.
        """
        return settled_month_across(profile, day, until or day) is not None

    def counted_into_a_closed_month(self, batch):
        """Whether anything this import wrote has since been counted into a closed month.

        Asked of the loader rather than of one table, because each kind of import
        writes somewhere different and each has to answer for its own rows. Asking
        only about hours meant an import of absences — which reduce the target, so
        they move the same balance — could be taken back out of a month that had
        already been agreed.
        """
        raise NotImplementedError


class TimeEntryLoader(_Loader):
    """Hours per person per day, from a spreadsheet."""

    kind = HrImportBatch.Kind.TIME_ENTRIES

    def check(self, rows):
        results = []
        for index, row in enumerate(rows, start=2):  # row 1 is the header
            email = row.get("email") or row.get("e_mail")
            profile = self.profile_for(email)
            day = _as_date(row.get("date") or row.get("datum"))
            minutes = _as_minutes(*_length_column(row))

            if profile is None:
                results.append(
                    RowResult(
                        index,
                        ERROR,
                        f"Nobody here logs in as {email or '(blank)'}.",
                        row,
                        "unknown_person",
                        {"email": email or ""},
                    )
                )
            elif day is None:
                results.append(RowResult(index, ERROR, "The date could not be read.", row, "bad_date"))
            elif minutes is None or minutes == 0:
                results.append(RowResult(index, ERROR, "The amount of time could not be read.", row, "bad_duration"))
            elif abs(minutes) > 1440:
                results.append(RowResult(index, ERROR, "More than a day in a single day.", row, "more_than_a_day"))
            elif self.month_is_closed(profile, day):
                results.append(RowResult(index, SKIP, "That month has been closed already.", row, "month_settled"))
            else:
                results.append(
                    RowResult(
                        index,
                        OK,
                        "",
                        {
                            "profile_id": str(profile.id),
                            "entry_date": day.isoformat(),
                            "minutes": minutes,
                            "note": row.get("note") or row.get("notiz") or "",
                        },
                    )
                )
        return results

    def write(self, batch, results):
        entries = [
            HrTimeEntry(
                workspace=self.workspace,
                profile_id=result.data["profile_id"],
                entry_date=result.data["entry_date"],
                minutes=int(result.data["minutes"]),
                category=HrTimeEntry.Category.IMPORTED,
                source=HrTimeEntry.Source.IMPORT,
                import_batch=batch,
                note=str(result.data.get("note") or ""),
            )
            for result in results
            if result.verdict == OK
        ]
        HrTimeEntry.objects.bulk_create(entries, batch_size=100)
        return len(entries)

    def counted_into_a_closed_month(self, batch):
        return HrTimeEntry.objects.filter(import_batch=batch, locked_period__isnull=False).exists()

    def undo(self, batch):
        return HrTimeEntry.objects.filter(import_batch=batch).delete()[0]


class OpeningBalanceLoader(_Loader):
    """What each person's balance was when the module started counting."""

    kind = HrImportBatch.Kind.OPENING_BALANCES

    KINDS = {
        "time": HrOpeningBalance.Kind.TIME_BALANCE,
        "zeit": HrOpeningBalance.Kind.TIME_BALANCE,
        "leave": HrOpeningBalance.Kind.LEAVE,
        "urlaub": HrOpeningBalance.Kind.LEAVE,
        "overtime": HrOpeningBalance.Kind.OVERTIME_BANK,
    }
    CONFIDENCE = {
        "documented": HrOpeningBalance.Confidence.EXACT,
        "exact": HrOpeningBalance.Confidence.EXACT,
        "reconstructed": HrOpeningBalance.Confidence.RECONSTRUCTED,
        "estimated": HrOpeningBalance.Confidence.ESTIMATED,
        "agreed": HrOpeningBalance.Confidence.AGREED,
    }

    def check(self, rows):
        results = []
        for index, row in enumerate(rows, start=2):
            email = row.get("email")
            profile = self.profile_for(email)
            day = _as_date(row.get("effective_on") or row.get("date"))
            minutes = _as_minutes(*_length_column(row))
            kind = self.KINDS.get(str(row.get("kind") or "time").strip().lower())
            basis = (row.get("basis") or row.get("grundlage") or "").strip()

            if profile is None:
                results.append(
                    RowResult(
                        index,
                        ERROR,
                        f"Nobody here logs in as {email or '(blank)'}.",
                        row,
                        "unknown_person",
                        {"email": email or ""},
                    )
                )
            elif day is None:
                results.append(RowResult(index, ERROR, "The date could not be read.", row, "bad_date"))
            elif minutes is None:
                results.append(RowResult(index, ERROR, "The balance could not be read.", row, "bad_balance"))
            elif kind is None:
                results.append(RowResult(index, ERROR, "Say whether this is time or leave.", row, "kind_missing"))
            elif not basis:
                # An opening balance without a stated basis is a number nobody can
                # defend when the person it belongs to disagrees with it.
                results.append(RowResult(index, ERROR, "Say what this figure is based on.", row, "basis_missing"))
            else:
                results.append(
                    RowResult(
                        index,
                        OK,
                        "",
                        {
                            "profile_id": str(profile.id),
                            "effective_on": day.isoformat(),
                            "minutes": minutes,
                            "kind": kind,
                            "basis": basis,
                            "confidence": self.CONFIDENCE.get(
                                str(row.get("confidence") or "agreed").strip().lower(),
                                HrOpeningBalance.Confidence.AGREED,
                            ),
                        },
                    )
                )
        return results

    def write(self, batch, results):
        rows = [
            HrOpeningBalance(
                workspace=self.workspace,
                profile_id=result.data["profile_id"],
                effective_on=result.data["effective_on"],
                kind=int(result.data["kind"]),
                minutes=int(result.data["minutes"]),
                confidence=int(result.data["confidence"]),
                basis=str(result.data["basis"]),
                import_batch=batch,
            )
            for result in results
            if result.verdict == OK
        ]
        HrOpeningBalance.objects.bulk_create(rows, batch_size=100)
        return len(rows)

    def counted_into_a_closed_month(self, batch):
        """An opening balance carries no lock of its own — it is not inside a month.

        It is what every later month is counted from, so the question is whether
        any month it opened has since been closed. Removing it afterwards would
        move a balance that has already been carried forward, agreed and paid on.
        """
        for profile_id, effective_on in (
            HrOpeningBalance.objects.filter(import_batch=batch).values_list("profile_id", "effective_on").distinct()
        ):
            if HrPeriod.objects.filter(
                profile_id=profile_id,
                state=HrPeriod.State.LOCKED,
                period_end__gte=effective_on,
            ).exists():
                return True
        return False

    def undo(self, batch):
        return HrOpeningBalance.objects.filter(import_batch=batch).delete()[0]


class AbsenceLoader(_Loader):
    """Leave and sickness already taken."""

    kind = HrImportBatch.Kind.ABSENCES

    def __init__(self, workspace):
        super().__init__(workspace)
        self._types = {
            absence_type.code.lower(): absence_type
            for absence_type in HrAbsenceType.objects.filter(workspace=workspace)
        }

    def check(self, rows):
        results = []
        for index, row in enumerate(rows, start=2):
            email = row.get("email")
            profile = self.profile_for(email)
            start = _as_date(row.get("start_date") or row.get("von"))
            end = _as_date(row.get("end_date") or row.get("bis")) or start
            code = str(row.get("type") or row.get("art") or "").strip().lower()
            absence_type = self._types.get(code)

            if profile is None:
                results.append(
                    RowResult(
                        index,
                        ERROR,
                        f"Nobody here logs in as {email or '(blank)'}.",
                        row,
                        "unknown_person",
                        {"email": email or ""},
                    )
                )
            elif start is None:
                results.append(RowResult(index, ERROR, "The start date could not be read.", row, "bad_start_date"))
            elif end < start:
                results.append(RowResult(index, ERROR, "It ends before it starts.", row, "ends_before_it_starts"))
            elif absence_type is None:
                results.append(
                    RowResult(
                        index,
                        ERROR,
                        f"There is no absence type '{code}'.",
                        row,
                        "unknown_absence_type",
                        {"code": code},
                    )
                )
            elif self.month_is_closed(profile, start, end):
                results.append(RowResult(index, SKIP, "That month has been closed already.", row, "month_settled"))
            else:
                results.append(
                    RowResult(
                        index,
                        OK,
                        "",
                        {
                            "profile_id": str(profile.id),
                            "absence_type_id": str(absence_type.id),
                            "start_date": start.isoformat(),
                            "end_date": end.isoformat(),
                        },
                    )
                )
        return results

    def write(self, batch, results):
        from plane.hr.services.absences import resolve_total_minutes

        written = 0
        for result in results:
            if result.verdict != OK:
                continue
            absence = HrAbsence.objects.create(
                workspace=self.workspace,
                profile_id=result.data["profile_id"],
                absence_type_id=result.data["absence_type_id"],
                start_date=result.data["start_date"],
                end_date=result.data["end_date"],
                state=HrAbsence.State.APPROVED,
                import_batch=batch,
                reason="Imported from a previous system.",
            )
            absence.total_minutes = resolve_total_minutes(absence)
            absence.save(update_fields=["total_minutes", "updated_at"])
            written += 1
        return written

    def counted_into_a_closed_month(self, batch):
        return HrAbsence.objects.filter(import_batch=batch, locked_period__isnull=False).exists()

    def undo(self, batch):
        return HrAbsence.objects.filter(import_batch=batch).delete()[0]


LOADERS = {
    HrImportBatch.Kind.TIME_ENTRIES: TimeEntryLoader,
    HrImportBatch.Kind.OPENING_BALANCES: OpeningBalanceLoader,
    HrImportBatch.Kind.ABSENCES: AbsenceLoader,
}


def prepare(batch, content):
    """Read a file and record what would happen, without writing anything."""
    loader = LOADERS[batch.kind](batch.workspace)
    rows = parse(content, batch.file_format)
    results = loader.check(rows)

    batch.row_count = len(results)
    batch.valid_count = sum(1 for result in results if result.verdict == OK)
    batch.error_count = sum(1 for result in results if result.verdict == ERROR)
    batch.preview = {"rows": [result.as_dict() for result in results]}
    batch.errors = [result.as_dict() for result in results if result.verdict == ERROR]
    batch.checksum = checksum(content)
    batch.state = HrImportBatch.State.PREVIEW_READY
    batch.save()
    return batch


@transaction.atomic
def commit(batch):
    """Write the rows that passed. Nothing else."""
    if batch.state != HrImportBatch.State.PREVIEW_READY:
        raise Refused("This import has not been checked, or has already been applied.", conflict=True)

    loader = LOADERS[batch.kind](batch.workspace)
    results = [
        RowResult(
            row["row"],
            row["verdict"],
            row["message"],
            row["data"],
            # Absent from previews stored before rows carried a reason. The
            # sentence is still there, so such a batch reads as it always did.
            row.get("reason", ""),
            row.get("detail"),
        )
        for row in batch.preview.get("rows", [])
    ]
    written = loader.write(batch, results)

    batch.state = HrImportBatch.State.COMMITTED
    batch.committed_at = timezone.now()
    batch.save()
    return written


@transaction.atomic
def undo(batch, actor, reason):
    """Take back everything one import wrote.

    Refused once any of it has been counted into a closed month — at that point
    the figures have been agreed with somebody, and quietly removing what they
    were based on is not an undo.
    """
    if batch.state != HrImportBatch.State.COMMITTED:
        raise Refused("Only an import that was applied can be undone.", conflict=True)
    if not (reason or "").strip():
        raise Refused("Say why the import is being undone.", conflict=True)

    loader = LOADERS[batch.kind](batch.workspace)
    if loader.counted_into_a_closed_month(batch):
        raise Refused(
            "Some of this has been counted into a month that is now closed. Reopen the month first.", conflict=True
        )

    removed = loader.undo(batch)

    batch.state = HrImportBatch.State.ROLLED_BACK
    batch.rolled_back_at = timezone.now()
    batch.rolled_back_by = actor if actor is not None and not actor.is_anonymous else None
    batch.rollback_reason = reason
    batch.save()
    return removed
