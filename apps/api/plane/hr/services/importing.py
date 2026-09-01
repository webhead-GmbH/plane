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
    raise ValueError("Only CSV and XLSX files can be read.")


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
    __slots__ = ("index", "verdict", "message", "data")

    def __init__(self, index, verdict, message="", data=None):
        self.index = index
        self.verdict = verdict
        self.message = message
        self.data = data or {}

    def as_dict(self):
        return {
            "row": self.index,
            "verdict": self.verdict,
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
                HrEmploymentProfile.objects.filter(
                    workspace=self.workspace, member__email__iexact=key
                )
                .select_related("member")
                .first()
            )
        return self._profiles[key]

    def month_is_closed(self, profile, day):
        return HrPeriod.objects.filter(
            profile=profile,
            state=HrPeriod.State.LOCKED,
            period_start__lte=day,
            period_end__gte=day,
        ).exists()


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
                    RowResult(index, ERROR, f"Nobody here logs in as {email or '(blank)'}.", row)
                )
            elif day is None:
                results.append(RowResult(index, ERROR, "The date could not be read.", row))
            elif minutes is None or minutes == 0:
                results.append(RowResult(index, ERROR, "The amount of time could not be read.", row))
            elif abs(minutes) > 1440:
                results.append(RowResult(index, ERROR, "More than a day in a single day.", row))
            elif self.month_is_closed(profile, day):
                results.append(
                    RowResult(index, SKIP, "That month has been closed already.", row)
                )
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
                    RowResult(index, ERROR, f"Nobody here logs in as {email or '(blank)'}.", row)
                )
            elif day is None:
                results.append(RowResult(index, ERROR, "The date could not be read.", row))
            elif minutes is None:
                results.append(RowResult(index, ERROR, "The balance could not be read.", row))
            elif kind is None:
                results.append(RowResult(index, ERROR, "Say whether this is time or leave.", row))
            elif not basis:
                # An opening balance without a stated basis is a number nobody can
                # defend when the person it belongs to disagrees with it.
                results.append(RowResult(index, ERROR, "Say what this figure is based on.", row))
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
                    RowResult(index, ERROR, f"Nobody here logs in as {email or '(blank)'}.", row)
                )
            elif start is None:
                results.append(RowResult(index, ERROR, "The start date could not be read.", row))
            elif end < start:
                results.append(RowResult(index, ERROR, "It ends before it starts.", row))
            elif absence_type is None:
                results.append(RowResult(index, ERROR, f"There is no absence type '{code}'.", row))
            elif self.month_is_closed(profile, start):
                results.append(RowResult(index, SKIP, "That month has been closed already.", row))
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
                reason=f"Imported from a previous system (batch {batch.id}).",
            )
            absence.total_minutes = resolve_total_minutes(absence)
            absence.save(update_fields=["total_minutes", "updated_at"])
            written += 1
        return written

    def undo(self, batch):
        # Absences carry no batch reference of their own, so they are found by the
        # note the import left on them.
        return HrAbsence.objects.filter(reason__contains=f"batch {batch.id}").delete()[0]


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
        raise ValueError("This import has not been checked, or has already been applied.")

    loader = LOADERS[batch.kind](batch.workspace)
    results = [
        RowResult(row["row"], row["verdict"], row["message"], row["data"])
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
        raise ValueError("Only an import that was applied can be undone.")
    if not (reason or "").strip():
        raise ValueError("Say why the import is being undone.")

    if HrTimeEntry.objects.filter(import_batch=batch, locked_period__isnull=False).exists():
        raise ValueError(
            "Some of these hours have been counted into a month that is now closed. "
            "Reopen the month first."
        )

    loader = LOADERS[batch.kind](batch.workspace)
    removed = loader.undo(batch)

    batch.state = HrImportBatch.State.ROLLED_BACK
    batch.rolled_back_at = timezone.now()
    batch.rolled_back_by = actor if actor is not None and not actor.is_anonymous else None
    batch.rollback_reason = reason
    batch.save()
    return removed
