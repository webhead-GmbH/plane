# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Keep an asset record in step with the file in storage.

A record is created before the browser sends the file to storage and confirmed
(``is_uploaded``) after, so the flag alone can be wrong both ways: a client can
confirm a file that never arrived, and a lost confirmation leaves a file that did
arrive looking unfinished. These helpers ask storage before either is acted on, and
never treat "storage could not answer" as "the file is missing".
"""

# Django imports
from django.conf import settings

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.settings.storage import PROBE_CLIENT_CONFIG, S3Storage, StorageUnavailable
from plane.utils.exception_logger import log_exception


def find_stored_file(asset):
    """The storage metadata of the asset's file, or None when storage has no such file.

    Raises StorageUnavailable when storage cannot be asked.
    """
    return S3Storage(client_config=PROBE_CLIENT_CONFIG).find_object(asset.asset.name)


def confirm_upload(asset):
    """Mark a freshly uploaded asset as uploaded, unless its file is certainly not in storage.

    Sets ``is_uploaded`` and, when storage answered, ``storage_metadata`` on the instance
    without saving it. Returns an error response when storage has no such file, else None.
    When storage cannot be asked, the client's word that the upload finished is taken,
    as before, so a file that did arrive is never turned away.
    """
    if asset.is_uploaded:
        return None
    try:
        metadata = find_stored_file(asset)
    except StorageUnavailable as e:
        log_exception(e)
        asset.is_uploaded = True
        return None
    if metadata is None:
        return Response(
            {
                "error": "The file is not in storage, so its upload did not finish. Upload the file again.",
                "code": "UPLOAD_NOT_FOUND",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    asset.is_uploaded = True
    asset.storage_metadata = metadata
    return None


def recover_upload(asset):
    """Make an asset that was never confirmed servable when its file is in storage after all.

    The confirmation that follows an upload can be lost (a dropped connection, a closed
    tab), which left the file stored but unreachable. Returns an error response when the
    asset cannot be served, else None, saving the asset when it was recovered.
    """
    if asset.is_uploaded:
        return None
    try:
        metadata = find_stored_file(asset)
    except StorageUnavailable as e:
        log_exception(e)
        return Response(
            {
                "error": "File storage cannot be reached right now. Try again in a few minutes.",
                "code": "STORAGE_UNAVAILABLE",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if metadata is None:
        return Response(
            {
                "error": "This file never finished uploading, so there is nothing to download. Upload it again.",
                "code": "ASSET_NOT_UPLOADED",
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    asset.is_uploaded = True
    asset.storage_metadata = metadata
    asset.save(update_fields=["is_uploaded", "storage_metadata"])
    return None


def file_too_large_response(size):
    """The response for an upload larger than FILE_SIZE_LIMIT, or None when it fits."""
    if size <= settings.FILE_SIZE_LIMIT:
        return None
    return Response(
        {
            "error": f"The file is too large. Files can be at most {settings.FILE_SIZE_LIMIT / (1024 * 1024):g} MB.",
            "code": "FILE_TOO_LARGE",
            "limit": settings.FILE_SIZE_LIMIT,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )
