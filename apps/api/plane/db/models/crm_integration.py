# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import models

# Module imports
from plane.db.models import BaseModel
from plane.license.utils.encryption import encrypt_data, decrypt_data


class CrmIntegration(BaseModel):
    """Per-workspace configuration for pushing monthly worklog summaries to a CRM.

    The CRM API key is stored encrypted at rest (Fernet, derived from
    ``SECRET_KEY``) and is only ever decrypted in-process when a request to the
    CRM is made.
    """

    class ProjectMappingSource(models.TextChoices):
        # Read the CRM project id from a workspace custom field on each project.
        CUSTOM_FIELD = "custom_field", "Custom field"
        # Use the project's own identifier (the "Project ID" in project settings),
        # which admins can set to the numeric CRM project id.
        IDENTIFIER = "identifier", "Project identifier"

    workspace = models.OneToOneField(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="crm_integration",
    )
    # Base URL of the CRM instance, e.g. https://crm.example.com
    crm_api_url = models.URLField(max_length=500)
    # CRM Bearer token, encrypted at rest. Never expose this field directly.
    crm_api_key_encrypted = models.TextField(blank=True, default="")
    # Where the CRM project id for each Plane project comes from.
    project_mapping_source = models.CharField(
        max_length=20,
        choices=ProjectMappingSource.choices,
        default=ProjectMappingSource.CUSTOM_FIELD,
    )
    # Plane custom field (entity_type="project") whose value holds the CRM project id.
    # Only consulted when project_mapping_source is "custom_field".
    crm_project_id_custom_field = models.ForeignKey(
        "db.CustomField",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_project_id_integration",
    )
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def set_api_key(self, raw_key):
        """Encrypt and store a raw CRM API key (pass an empty value to clear it)."""
        self.crm_api_key_encrypted = encrypt_data(raw_key) if raw_key else ""

    def get_api_key(self):
        """Return the decrypted CRM API key, or an empty string when unset."""
        if not self.crm_api_key_encrypted:
            return ""
        return decrypt_data(self.crm_api_key_encrypted)

    def __str__(self):
        return f"{self.workspace.slug} CRM integration"

    class Meta:
        verbose_name = "CRM Integration"
        verbose_name_plural = "CRM Integrations"
        db_table = "crm_integrations"
        ordering = ("-created_at",)


class CrmTaskLink(BaseModel):
    """Ties one Plane work item to the CRM task that mirrors it.

    The link is what makes the sync idempotent: its presence means the work item
    already exists in the CRM, so later edits become updates rather than
    duplicate tasks. Sub work items get their own link and their own ordinary CRM
    task — the CRM has no notion of a parent task here.
    """

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="crm_task_links")
    issue = models.OneToOneField("db.Issue", on_delete=models.CASCADE, related_name="crm_task_link")
    crm_task_id = models.PositiveIntegerField()
    # CRM project the task was filed under, kept so a project remap can be detected.
    crm_project_id = models.PositiveIntegerField()
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"issue {self.issue_id} -> CRM task {self.crm_task_id}"

    class Meta:
        verbose_name = "CRM Task Link"
        verbose_name_plural = "CRM Task Links"
        db_table = "crm_task_links"
        ordering = ("-created_at",)


class CrmTimerLink(BaseModel):
    """Ties one Plane worklog (or running timer) to its CRM timer row."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="crm_timer_links")
    worklog = models.OneToOneField("db.IssueWorkLog", on_delete=models.CASCADE, related_name="crm_timer_link")
    crm_timer_id = models.PositiveIntegerField()
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"worklog {self.worklog_id} -> CRM timer {self.crm_timer_id}"

    class Meta:
        verbose_name = "CRM Timer Link"
        verbose_name_plural = "CRM Timer Links"
        db_table = "crm_timer_links"
        ordering = ("-created_at",)
