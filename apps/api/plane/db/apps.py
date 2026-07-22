# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig


class DbConfig(AppConfig):
    name = "plane.db"

    def ready(self):
        # Registers the CRM mirroring receivers. Imported here rather than at
        # module level so the models are loaded by the time the handlers bind.
        from . import signals  # noqa: F401
