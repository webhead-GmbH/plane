# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The nightly cleanup of unfinished uploads, and the command that undoes its old mistakes.

The cleanup removed every record left unconfirmed for a week without looking in
storage, so a file whose confirmation was lost disappeared from Plane for good. It
now asks storage first. These run against the test stack's real storage server.
"""

from datetime import timedelta
from io import BytesIO
from unittest import mock
from uuid import uuid4

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from plane.bgtasks.file_asset_task import delete_unuploaded_file_asset
from plane.db.models import FileAsset
from plane.settings.storage import S3Storage, StorageUnavailable


def unfinished(workspace, user, *, days_old=8, stored=False, **fields):
    asset = FileAsset(
        attributes={"name": "photo.png", "type": "image/png", "size": 3},
        asset=f"{workspace.id}/{uuid4().hex}-photo.png",
        size=3,
        workspace=workspace,
        entity_type=FileAsset.EntityTypeContext.ISSUE_DESCRIPTION,
        is_uploaded=False,
        **fields,
    )
    asset.save(created_by_id=user.id)
    FileAsset.all_objects.filter(pk=asset.pk).update(created_at=timezone.now() - timedelta(days=days_old))
    if stored:
        assert S3Storage().upload_file(BytesIO(b"png"), asset.asset.name, "image/png")
    return asset


def state(asset):
    asset = FileAsset.all_objects.get(pk=asset.pk)
    return asset.is_uploaded, asset.deleted_at is not None


@pytest.mark.unit
@pytest.mark.django_db
class TestCleanupOfUnfinishedUploads:
    def test_a_record_without_a_file_is_removed(self, workspace, create_user):
        asset = unfinished(workspace, create_user)

        delete_unuploaded_file_asset()

        assert state(asset) == (False, True)

    def test_a_record_whose_file_is_stored_is_confirmed_instead(self, workspace, create_user):
        asset = unfinished(workspace, create_user, stored=True)

        delete_unuploaded_file_asset()

        assert state(asset) == (True, False)
        assert FileAsset.objects.get(pk=asset.pk).storage_metadata["ContentLength"] == 3

    def test_a_recent_record_is_left_alone(self, workspace, create_user):
        asset = unfinished(workspace, create_user, days_old=1)

        delete_unuploaded_file_asset()

        assert state(asset) == (False, False)

    def test_nothing_is_removed_while_storage_cannot_be_reached(self, workspace, create_user):
        asset = unfinished(workspace, create_user)

        with mock.patch.object(S3Storage, "find_object", side_effect=StorageUnavailable("down")):
            delete_unuploaded_file_asset()

        assert state(asset) == (False, False)


@pytest.mark.unit
@pytest.mark.django_db
class TestRecoveringUnfinishedUploads:
    def test_a_stored_file_is_recovered_and_a_missing_one_is_left(self, workspace, create_user):
        stored = unfinished(workspace, create_user, stored=True)
        missing = unfinished(workspace, create_user)

        call_command("recover_unfinished_uploads")

        assert state(stored) == (True, False)
        assert state(missing) == (False, False)

    def test_a_dry_run_changes_nothing(self, workspace, create_user):
        stored = unfinished(workspace, create_user, stored=True)

        call_command("recover_unfinished_uploads", "--dry-run")

        assert state(stored) == (False, False)

    def test_records_the_old_cleanup_removed_come_back_only_when_asked(self, workspace, create_user):
        removed = unfinished(workspace, create_user, stored=True)
        FileAsset.objects.filter(pk=removed.pk).delete()

        call_command("recover_unfinished_uploads")
        assert state(removed) == (False, True)

        call_command("recover_unfinished_uploads", "--include-deleted")
        assert state(removed) == (True, False)

    def test_what_a_person_deleted_stays_deleted(self, workspace, create_user):
        deleted = unfinished(workspace, create_user, stored=True, is_deleted=True, deleted_at=timezone.now())

        call_command("recover_unfinished_uploads", "--include-deleted")

        assert state(deleted) == (False, True)

    def test_it_stops_when_storage_cannot_be_reached(self, workspace, create_user):
        unfinished(workspace, create_user)

        with (
            mock.patch.object(S3Storage, "find_object", side_effect=StorageUnavailable("down")),
            pytest.raises(CommandError),
        ):
            call_command("recover_unfinished_uploads")
