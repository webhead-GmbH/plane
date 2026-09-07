# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Getting old data in, and finished months out."""

# Python imports
from datetime import date
from uuid import uuid4

# Django imports
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify

# Third-party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.views.base import BaseAPIView
from plane.hr.models import HrImportBatch, HrPeriod
from plane.hr.utils.company import hr_home_workspace
from plane.hr.permissions import (
    MANAGER,
    SELF,
    hr_permission,
    readable_profile_or_none,
    visible_profiles,
)
from plane.hr.services import exporting, importing

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _requested_format(request):
    """Which file shape the caller wants.

    Deliberately not called ``format``: the API framework reserves that query
    parameter to pick its own renderer, and passing an unknown value there makes
    the request fail as not found before the view is ever reached.
    """
    return request.query_params.get("file_format", "csv")


def _batch_payload(batch):
    return {
        "id": str(batch.id),
        "kind": batch.kind,
        "state": batch.state,
        "filename": batch.filename,
        "row_count": batch.row_count,
        "valid_count": batch.valid_count,
        "error_count": batch.error_count,
        "skipped_count": batch.row_count - batch.valid_count - batch.error_count,
        "preview": batch.preview.get("rows", []),
        "committed_at": batch.committed_at,
        "rolled_back_at": batch.rolled_back_at,
        "rollback_reason": batch.rollback_reason,
    }


class HrImportEndpoint(BaseAPIView):
    """Upload a file and see exactly what it would do, before it does it."""

    @hr_permission(MANAGER)
    def get(self, request, pk=None):
        batches = HrImportBatch.objects.order_by("-created_at")
        if pk is not None:
            batch = batches.filter(pk=pk).first()
            if batch is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(_batch_payload(batch), status=status.HTTP_200_OK)
        return Response(
            [{**_batch_payload(batch), "preview": []} for batch in batches],
            status=status.HTTP_200_OK,
        )

    @hr_permission(MANAGER)
    def post(self, request):
        workspace = hr_home_workspace()

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"error": "Attach a file."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > MAX_UPLOAD_BYTES:
            return Response(
                {"error": "That file is larger than this accepts."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            kind = int(request.data.get("kind", HrImportBatch.Kind.TIME_ENTRIES))
        except (TypeError, ValueError):
            return Response({"error": "Say what kind of data this is."}, status=status.HTTP_400_BAD_REQUEST)
        if kind not in importing.LOADERS:
            return Response(
                {"error": "That kind of import is not supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        name = upload.name or "upload"
        file_format = "xlsx" if name.lower().endswith((".xlsx", ".xls")) else "csv"
        content = upload.read()

        # The same file applied twice would double every hour in it.
        digest = importing.checksum(content)
        already = HrImportBatch.objects.filter(
            kind=kind,
            checksum=digest,
            state=HrImportBatch.State.COMMITTED,
        ).first()
        if already is not None:
            return Response(
                {
                    "error": "This exact file has already been applied.",
                    "batch_id": str(already.id),
                },
                status=status.HTTP_409_CONFLICT,
            )

        batch = HrImportBatch.objects.create(
            workspace=workspace,
            initiated_by=request.user,
            kind=kind,
            filename=name,
            file_format=file_format,
            state=HrImportBatch.State.VALIDATING,
        )
        try:
            importing.prepare(batch, content)
        except ValueError as invalid:
            batch.state = HrImportBatch.State.FAILED
            batch.errors = [{"message": str(invalid)}]
            batch.save()
            return Response({"error": str(invalid)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:  # noqa: BLE001 - a malformed file must not be a server error
            batch.state = HrImportBatch.State.FAILED
            batch.errors = [{"message": "The file could not be read."}]
            batch.save()
            return Response(
                {"error": "The file could not be read. Check it is a CSV or XLSX."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(_batch_payload(batch), status=status.HTTP_201_CREATED)


class HrImportCommitEndpoint(BaseAPIView):
    @hr_permission(MANAGER)
    def post(self, request, pk):
        batch = HrImportBatch.objects.filter(pk=pk).first()
        if batch is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            written = importing.commit(batch)
        except ValueError as invalid:
            return Response({"error": str(invalid)}, status=status.HTTP_409_CONFLICT)
        return Response({**_batch_payload(batch), "written": written}, status=status.HTTP_200_OK)


class HrImportUndoEndpoint(BaseAPIView):
    @hr_permission(MANAGER)
    def post(self, request, pk):
        batch = HrImportBatch.objects.filter(pk=pk).first()
        if batch is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            removed = importing.undo(batch, request.user, request.data.get("reason", ""))
        except ValueError as invalid:
            return Response({"error": str(invalid)}, status=status.HTTP_409_CONFLICT)
        return Response({**_batch_payload(batch), "removed": removed}, status=status.HTTP_200_OK)


class HrMonthExportEndpoint(BaseAPIView):
    """A month for everybody, in the shape payroll expects."""

    @hr_permission(MANAGER)
    def get(self, request):
        try:
            year = int(request.query_params.get("year"))
            month = int(request.query_params.get("month"))
            first = date(year, month, 1)
        except (TypeError, ValueError):
            return Response(
                {"error": "Say which month, as year and month."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_format = _requested_format(request)
        periods = (
            HrPeriod.objects.filter(profile__in=visible_profiles(request), period_start=first)
            .select_related("profile__member")
            .order_by("profile__member__email")
        )
        try:
            payload, content_type = exporting.render(
                exporting.month_rows(periods), exporting.MONTH_COLUMNS, file_format
            )
        except ValueError as invalid:
            return Response({"error": str(invalid)}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(payload, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="hr-{year}-{month:02d}.{file_format}"'
        return response


class HrPeriodExportEndpoint(BaseAPIView):
    """One person's month, day by day."""

    @hr_permission(SELF)
    def get(self, request, pk):
        period = (
            HrPeriod.objects.filter(pk=pk, profile__in=visible_profiles(request))
            .select_related("profile__member")
            .first()
        )
        if period is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        file_format = _requested_format(request)
        try:
            payload, content_type = exporting.render(exporting.day_rows(period), exporting.DAY_COLUMNS, file_format)
        except ValueError as invalid:
            return Response({"error": str(invalid)}, status=status.HTTP_400_BAD_REQUEST)

        stamp = period.period_start.strftime("%Y-%m")
        # Named after the person as well as the month. Every one of these was
        # called the same thing, so a manager saving the team's files into one
        # folder ended up with one file and a row of "(1)", "(2)" beside it.
        who = slugify(period.profile.member.display_name or period.profile.member.email or "") or "person"
        response = HttpResponse(payload, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="hr-{stamp}-{who}.{file_format}"'
        return response


class HrOpeningBalanceAcknowledgeEndpoint(BaseAPIView):
    """The person says the figure they were given is right.

    Scoped to the person themselves rather than to whoever looks after the team.
    The whole worth of an agreed figure is that the person it belongs to agreed
    it, and a manager who could tick that box on their behalf would be recording
    their own opinion twice.
    """

    @hr_permission(SELF)
    def post(self, request, profile_id, pk):
        from plane.hr.models import HrOpeningBalance

        own = getattr(request, "hr_profile", None)
        if own is None or str(own.id) != str(profile_id):
            return Response(
                {"error": "Only the person a balance belongs to can agree it."},
                status=status.HTTP_403_FORBIDDEN,
            )

        row = HrOpeningBalance.objects.filter(profile_id=own.id, pk=pk).first()
        if row is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.superseded_by_id is not None:
            return Response(
                {"error": "That figure has already been replaced by a corrected one."},
                status=status.HTTP_409_CONFLICT,
            )
        if row.acknowledged_at is not None:
            return Response({"already_agreed": True}, status=status.HTTP_200_OK)

        row.acknowledged_by = request.user
        row.acknowledged_at = timezone.now()
        row.save(update_fields=["acknowledged_by", "acknowledged_at", "updated_at"])
        return Response(
            {"id": str(row.id), "acknowledged_at": row.acknowledged_at},
            status=status.HTTP_200_OK,
        )


class HrOpeningBalanceEndpoint(BaseAPIView):
    """What somebody's balance was when the module started counting for them."""

    @hr_permission(SELF)
    def get(self, request, profile_id):
        from plane.hr.models import HrOpeningBalance

        profile = readable_profile_or_none(request, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        rows = HrOpeningBalance.objects.filter(profile_id=profile.id).order_by("-effective_on")
        return Response(
            [
                {
                    "id": str(row.id),
                    "effective_on": row.effective_on,
                    "kind": row.kind,
                    "minutes": row.minutes,
                    "confidence": row.confidence,
                    "basis": row.basis,
                    "superseded_by": str(row.superseded_by_id) if row.superseded_by_id else None,
                    "acknowledged_at": row.acknowledged_at,
                }
                for row in rows
            ],
            status=status.HTTP_200_OK,
        )

    @hr_permission(MANAGER)
    def post(self, request, profile_id):
        from plane.hr.models import HrOpeningBalance

        profile = readable_profile_or_none(request, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        basis = (request.data.get("basis") or "").strip()
        if not basis:
            # A figure nobody can account for is one nobody can defend when the
            # person it belongs to disagrees with it.
            return Response({"error": "Say what this figure is based on."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            minutes = int(request.data.get("minutes"))
            kind = int(request.data.get("kind", HrOpeningBalance.Kind.TIME_BALANCE))
        except (TypeError, ValueError):
            return Response({"error": "The balance could not be read."}, status=status.HTTP_400_BAD_REQUEST)

        row = HrOpeningBalance.objects.create(
            workspace_id=profile.workspace_id,
            profile=profile,
            effective_on=request.data.get("effective_on"),
            kind=kind,
            minutes=minutes,
            confidence=int(request.data.get("confidence", HrOpeningBalance.Confidence.AGREED)),
            basis=basis,
        )
        return Response({"id": str(row.id)}, status=status.HTTP_201_CREATED)

    @hr_permission(MANAGER)
    def patch(self, request, profile_id, pk):
        """Replace a figure with a corrected one, keeping the original readable."""
        from plane.hr.models import HrOpeningBalance

        profile = readable_profile_or_none(request, profile_id)
        if profile is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        old = HrOpeningBalance.objects.filter(profile_id=profile.id, pk=pk).first()
        if old is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        basis = (request.data.get("basis") or "").strip()
        if not basis:
            return Response(
                {"error": "Say what the corrected figure is based on."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            minutes = int(request.data.get("minutes"))
        except (TypeError, ValueError):
            return Response({"error": "The balance could not be read."}, status=status.HTTP_400_BAD_REQUEST)

        # Only one figure per person, kind and date may be the current one, so the
        # old row has to stop being current before the new one exists. Its id is
        # chosen here rather than by the database so the old row can point at it
        # first; the reference itself is only checked when the transaction
        # commits, by which time the row it names is there.
        replacement_id = uuid4()
        with transaction.atomic():
            old.superseded_by_id = replacement_id
            old.save(update_fields=["superseded_by", "updated_at"])
            replacement = HrOpeningBalance.objects.create(
                id=replacement_id,
                workspace_id=profile.workspace_id,
                profile=profile,
                effective_on=old.effective_on,
                kind=old.kind,
                minutes=minutes,
                confidence=int(request.data.get("confidence", old.confidence)),
                basis=basis,
            )
        return Response({"id": str(replacement.id)}, status=status.HTTP_200_OK)
