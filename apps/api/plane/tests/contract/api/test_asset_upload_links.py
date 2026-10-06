# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The public API's asset endpoints, with the storage class left as it is.

Three of them build it with ``is_server=True``, an argument it did not take: every
call ended in a ``TypeError`` and a 500. The tests beside this one replace the class
with a mock, which is why they never met it.
"""

import pytest
from rest_framework import status

from plane.db.models import FileAsset
from plane.settings.storage import S3Storage


@pytest.mark.unit
def test_the_storage_class_takes_the_argument_the_public_api_passes():
    S3Storage(request=None, is_server=True)


@pytest.mark.contract
@pytest.mark.django_db
class TestAssetUploadLinks:
    def test_a_server_upload_for_a_user_gets_its_link(self, api_key_client):
        response = api_key_client.post(
            "/api/v1/assets/user-assets/server/",
            {"name": "avatar.png", "type": "image/png", "size": 1024, "entity_type": "USER_AVATAR"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["upload_data"]["fields"]["Content-Type"] == "image/png"

    def test_a_generic_asset_gets_its_link_and_can_be_read_back(self, api_key_client, workspace):
        created = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/assets/",
            {"name": "report.pdf", "type": "application/pdf", "size": 1024},
            format="json",
        )
        assert created.status_code == status.HTTP_200_OK
        asset = FileAsset.objects.get(id=created.data["asset_id"])
        asset.is_uploaded = True
        asset.save(update_fields=["is_uploaded"])

        read = api_key_client.get(f"/api/v1/workspaces/{workspace.slug}/assets/{asset.id}/")

        assert read.status_code == status.HTTP_200_OK
        assert asset.asset.name in read.data["asset_url"]

    def test_a_generic_text_asset_sent_without_a_type_is_accepted(self, api_key_client, workspace):
        response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/assets/",
            {"name": "notes.md", "type": "", "size": 120},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert FileAsset.objects.get(id=response.data["asset_id"]).attributes["type"] == "text/markdown"
