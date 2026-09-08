# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Taking back an import, and the two things that must stop it.

An undo removes what one import wrote. It has to find exactly those rows and no
others, and it has to refuse once any of them has been counted into a month that
was closed on the strength of them — at that point somebody has agreed the
figures, and quietly removing what they were based on is not an undo.

Absences matter here as much as hours: they reduce the target, so they move the
same balance. An undo that asked only about hours would take an agreed month's
leave back out of it without a word.
"""

# Python imports
from datetime import date
from uuid import uuid4

# Third party imports
import pytest

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
from plane.hr.services.importing import undo
from plane.tests.factories import UserFactory, WorkspaceFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

MARCH = date(2026, 3, 1)


@pytest.fixture
def workspace():
    return WorkspaceFactory(owner=UserFactory(username=uuid4().hex))


@pytest.fixture
def profile(workspace):
    return HrEmploymentProfile.objects.create(
        workspace=workspace,
        member=UserFactory(username=uuid4().hex),
        timezone="Europe/Vienna",
        hire_date=date(2024, 1, 1),
    )


def a_batch(workspace, kind):
    return HrImportBatch.objects.create(
        workspace=workspace,
        kind=kind,
        state=HrImportBatch.State.COMMITTED,
        filename="last-year.csv",
    )


def a_closed_march(profile):
    return HrPeriod.objects.create(
        workspace=profile.workspace,
        profile=profile,
        period_start=MARCH,
        period_end=date(2026, 3, 31),
        state=HrPeriod.State.LOCKED,
        target_minutes=9240,
        actual_minutes=9240,
        balance_minutes=0,
    )


def an_absence(workspace, profile, batch, locked_period=None):
    absence_type = HrAbsenceType.objects.create(
        workspace=workspace, code=uuid4().hex[:8], name_de="Urlaub", credits_actual=True
    )
    return HrAbsence.objects.create(
        workspace=workspace,
        profile=profile,
        absence_type=absence_type,
        start_date=date(2026, 3, 2),
        end_date=date(2026, 3, 2),
        state=HrAbsence.State.APPROVED,
        import_batch=batch,
        locked_period=locked_period,
        reason="Imported from a previous system.",
    )


class TestAnUndoStopsAtAClosedMonth:
    def test_absences_counted_into_a_closed_month_refuse_the_undo(self, workspace, profile):
        """The case the guard used to miss entirely: it only asked about hours."""
        batch = a_batch(workspace, HrImportBatch.Kind.ABSENCES)
        an_absence(workspace, profile, batch, locked_period=a_closed_march(profile))

        with pytest.raises(Refused, match="closed"):
            undo(batch, profile.member, "Wrong file")

        assert HrAbsence.objects.filter(import_batch=batch).count() == 1

    def test_absences_that_no_closed_month_counted_come_back_out(self, workspace, profile):
        batch = a_batch(workspace, HrImportBatch.Kind.ABSENCES)
        an_absence(workspace, profile, batch)

        assert undo(batch, profile.member, "Wrong file") == 1
        assert not HrAbsence.objects.filter(import_batch=batch).exists()

    def test_hours_counted_into_a_closed_month_still_refuse_it(self, workspace, profile):
        batch = a_batch(workspace, HrImportBatch.Kind.TIME_ENTRIES)
        HrTimeEntry.objects.create(
            workspace=workspace,
            profile=profile,
            entry_date=date(2026, 3, 2),
            minutes=60,
            import_batch=batch,
            locked_period=a_closed_march(profile),
        )

        with pytest.raises(Refused, match="closed"):
            undo(batch, profile.member, "Wrong file")

    def test_an_opening_balance_a_closed_month_was_counted_from_refuses_it(self, workspace, profile):
        """An opening balance sits before every month, so it carries no lock of its own.

        Removing it would move a figure that has already been carried forward
        through a month somebody agreed and was paid on.
        """
        batch = a_batch(workspace, HrImportBatch.Kind.OPENING_BALANCES)
        HrOpeningBalance.objects.create(
            workspace=workspace,
            profile=profile,
            effective_on=date(2026, 1, 1),
            kind=HrOpeningBalance.Kind.TIME_BALANCE,
            minutes=600,
            basis="Agreed with the person",
            import_batch=batch,
        )
        a_closed_march(profile)

        with pytest.raises(Refused, match="closed"):
            undo(batch, profile.member, "Wrong figures")

    def test_an_opening_balance_no_closed_month_has_reached_yet_comes_back_out(self, workspace, profile):
        batch = a_batch(workspace, HrImportBatch.Kind.OPENING_BALANCES)
        HrOpeningBalance.objects.create(
            workspace=workspace,
            profile=profile,
            effective_on=date(2026, 6, 1),
            kind=HrOpeningBalance.Kind.TIME_BALANCE,
            minutes=600,
            basis="Agreed with the person",
            import_batch=batch,
        )
        a_closed_march(profile)  # Closed, but before the balance takes effect.

        assert undo(batch, profile.member, "Wrong figures") == 1


class TestAnUndoFindsItsOwnRows:
    def test_it_takes_back_only_what_this_import_wrote(self, workspace, profile):
        """Rows are named by the batch that wrote them, not recognised by their wording.

        They used to be found by a phrase left in the reason — a field the person
        whose absence it is can edit, so an absence could be kept out of an undo
        by rewriting a sentence, or swept into somebody else's by copying one in.
        """
        mine = a_batch(workspace, HrImportBatch.Kind.ABSENCES)
        theirs = a_batch(workspace, HrImportBatch.Kind.ABSENCES)
        an_absence(workspace, profile, mine)
        survivor = an_absence(workspace, profile, theirs)

        assert undo(mine, profile.member, "Wrong file") == 1
        assert HrAbsence.objects.filter(pk=survivor.pk).exists()

    def test_rewriting_the_reason_does_not_hide_a_row_from_its_undo(self, workspace, profile):
        batch = a_batch(workspace, HrImportBatch.Kind.ABSENCES)
        absence = an_absence(workspace, profile, batch)
        HrAbsence.objects.filter(pk=absence.pk).update(reason="Agreed with my manager")

        assert undo(batch, profile.member, "Wrong file") == 1
        assert not HrAbsence.objects.filter(pk=absence.pk).exists()

    def test_an_absence_nobody_imported_is_left_alone(self, workspace, profile):
        batch = a_batch(workspace, HrImportBatch.Kind.ABSENCES)
        an_absence(workspace, profile, batch)
        own = an_absence(workspace, profile, None)
        HrAbsence.objects.filter(pk=own.pk).update(reason=f"Booked myself, like batch {batch.id}")

        undo(batch, profile.member, "Wrong file")

        assert HrAbsence.objects.filter(pk=own.pk).exists()


class TestAnUndoSaysWhy:
    def test_it_refuses_without_a_reason(self, workspace, profile):
        batch = a_batch(workspace, HrImportBatch.Kind.ABSENCES)
        with pytest.raises(Refused, match="why"):
            undo(batch, profile.member, "   ")

    def test_it_refuses_an_import_that_was_never_applied(self, workspace, profile):
        batch = a_batch(workspace, HrImportBatch.Kind.ABSENCES)
        HrImportBatch.objects.filter(pk=batch.pk).update(state=HrImportBatch.State.PREVIEW_READY)
        batch.refresh_from_db()

        with pytest.raises(Refused, match="applied"):
            undo(batch, profile.member, "Wrong file")
