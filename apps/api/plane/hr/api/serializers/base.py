# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third-party imports
from rest_framework import serializers


class HrBaseSerializer(serializers.ModelSerializer):
    """Defined here rather than imported so the module stays self-contained."""

    id = serializers.PrimaryKeyRelatedField(read_only=True)
