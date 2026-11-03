# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig


class GdriveConfig(AppConfig):
    name = "plane.gdrive"
    label = "gdrive"

    def ready(self):
        from plane.gdrive import signals  # noqa: F401 — connects the receivers
