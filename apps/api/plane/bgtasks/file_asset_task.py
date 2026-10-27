# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import logging
import os
from datetime import timedelta

# Django imports
from django.utils import timezone

# Third party imports
from celery import shared_task

# Module imports
from plane.db.models import FileAsset
from plane.settings.storage import PROBE_CLIENT_CONFIG, S3Storage, StorageUnavailable

logger = logging.getLogger("plane.worker")


@shared_task
def delete_unuploaded_file_asset():
    """Clear out the records of uploads that never finished.

    A record is created before the browser sends the file to storage and confirmed
    after it, so a record left unconfirmed usually means the upload failed. But the
    file may have reached storage while the confirmation was lost, so storage is asked
    first: a record whose file is there is confirmed and kept, only a record whose
    file is certainly missing is removed, and nothing is decided while storage cannot
    be reached.
    """
    cutoff = timezone.now() - timedelta(days=int(os.environ.get("UNUPLOADED_ASSET_DELETE_DAYS", "7")))
    storage = S3Storage(client_config=PROBE_CLIENT_CONFIG)
    recovered = removed = 0
    for asset in FileAsset.objects.filter(created_at__lt=cutoff, is_uploaded=False).iterator():
        try:
            metadata = storage.find_object(asset.asset.name)
        except StorageUnavailable as e:
            logger.warning("Storage cannot be reached, unfinished uploads are left alone: %s", e)
            break
        if metadata is None:
            # A soft delete of the row alone, as before; the hard delete task purges it later
            FileAsset.objects.filter(pk=asset.pk).delete()
            removed += 1
        else:
            asset.is_uploaded = True
            asset.storage_metadata = metadata
            asset.save(update_fields=["is_uploaded", "storage_metadata"], disable_auto_set_user=True)
            recovered += 1
    if recovered or removed:
        logger.info("Unfinished uploads: %s found in storage and kept, %s removed", recovered, removed)
