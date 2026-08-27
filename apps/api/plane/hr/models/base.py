# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Base class for every model in this module.

Deliberately *not* ``plane.db.models.BaseModel``. That class carries
``deleted_at`` through ``SoftDeleteModel``, and the daily cleanup task ends with
a sweep over ``apps.get_models()`` that hard-deletes every row of every model
having that field once it is older than the retention window
(``plane/bgtasks/deletion_task.py``). Records here are the basis of what people
are paid and have to outlive that by years, so they simply do not have the field
the sweep looks for.

Where a record needs to be withdrawn, the model says so explicitly — an
``is_active`` flag, a ``superseded_by`` pointer, or a state column — so that
withdrawal is a visible, auditable act rather than a hidden one.
"""

# Python imports
import uuid

# Django imports
from django.db import models

# Third-party imports
from crum import get_current_user


class HrBaseModel(models.Model):
    id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last Modified At")
    created_by = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        related_name="hr_%(class)s_created_by",
        verbose_name="Created By",
        null=True,
    )
    updated_by = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        related_name="hr_%(class)s_updated_by",
        verbose_name="Last Modified By",
        null=True,
    )

    class Meta:
        abstract = True

    def save(self, *args, disable_auto_set_user=False, **kwargs):
        # Mirrors plane.db.models.BaseModel so that authorship is populated the
        # same way everywhere. Background tasks pass disable_auto_set_user, since
        # there is no request user to attribute the write to.
        if not disable_auto_set_user:
            user = get_current_user()
            if user is None or user.is_anonymous:
                pass
            elif self._state.adding:
                self.created_by = user
            else:
                self.updated_by = user
        super().save(*args, **kwargs)
