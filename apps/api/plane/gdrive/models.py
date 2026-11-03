# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Which Google Drive account a workspace uses, and where each project's files live in it."""

# Django imports
from django.conf import settings
from django.db import models

# Module imports
from plane.db.models import BaseModel
from plane.license.utils.encryption import decrypt_data, encrypt_data


class DriveConnection(BaseModel):
    """One workspace's Google Drive: the account it acts as, and where the project folders are.

    The OAuth client is the company's own (made once in Google Cloud), so its id
    and secret are kept here rather than in the server's environment, where
    changing them would need a redeploy. The secret and the refresh token are
    encrypted at rest and only decrypted for a call to Google.
    """

    workspace = models.OneToOneField("db.Workspace", on_delete=models.CASCADE, related_name="drive_connection")
    client_id = models.CharField(max_length=255, blank=True, default="")
    client_secret_encrypted = models.TextField(blank=True, default="")
    refresh_token_encrypted = models.TextField(blank=True, default="")
    account_email = models.CharField(max_length=255, blank=True, default="")
    connected_at = models.DateTimeField(null=True, blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # The folder the project folders are in, e.g. "projects / webhead". Only its
    # direct subfolders are offered for projects, so the whole Drive is not.
    root_folder_id = models.CharField(max_length=255, blank=True, default="")
    root_folder_name = models.CharField(max_length=255, blank=True, default="")
    root_folder_path = models.CharField(max_length=1024, blank=True, default="")
    # A new project gets a folder of its own, or the existing one its name matches.
    auto_link_new_projects = models.BooleanField(default=True)

    class Meta:
        db_table = "gdrive_connections"
        verbose_name = "Google Drive connection"

    def set_client_secret(self, secret):
        self.client_secret_encrypted = encrypt_data(secret) if secret else ""

    def get_client_secret(self):
        return decrypt_data(self.client_secret_encrypted) if self.client_secret_encrypted else ""

    def set_refresh_token(self, token):
        self.refresh_token_encrypted = encrypt_data(token) if token else ""

    def get_refresh_token(self):
        return decrypt_data(self.refresh_token_encrypted) if self.refresh_token_encrypted else ""

    @property
    def is_connected(self):
        return bool(self.refresh_token_encrypted)

    @property
    def is_ready(self):
        """Connected, and told where the project folders are."""
        return self.is_connected and bool(self.root_folder_id)


class DriveProjectFolder(BaseModel):
    """The Drive folder a project's files go to."""

    class Method(models.TextChoices):
        CHOSEN = "chosen", "Chosen by hand"
        MATCHED = "matched", "Matched by name"
        CREATED = "created", "Created by Plane"

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    project = models.OneToOneField("db.Project", on_delete=models.CASCADE, related_name="drive_folder")
    folder_id = models.CharField(max_length=255)
    folder_name = models.CharField(max_length=255, blank=True, default="")
    # The "Tasks" folder inside it, once one has been found or made.
    tasks_folder_id = models.CharField(max_length=255, blank=True, default="")
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.CHOSEN)

    class Meta:
        db_table = "gdrive_project_folders"
        verbose_name = "Google Drive project folder"


class DriveIssueFolder(BaseModel):
    """The folder inside "Tasks" that one work item's files go to, e.g. "WEB-42"."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="+")
    issue = models.OneToOneField("db.Issue", on_delete=models.CASCADE, related_name="drive_folder")
    folder_id = models.CharField(max_length=255)
    folder_name = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "gdrive_issue_folders"
        verbose_name = "Google Drive work item folder"


class DriveFile(BaseModel):
    """A file a work item has in Drive: attached to it, or put in its description or a comment."""

    class Source(models.TextChoices):
        ATTACHMENT = "attachment", "Attachment"
        DESCRIPTION = "description", "Description"
        COMMENT = "comment", "Comment"

    class State(models.TextChoices):
        UPLOADING = "uploading", "Uploading"
        UPLOADED = "uploaded", "Uploaded"

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="+")
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="drive_files")
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.ATTACHMENT)
    state = models.CharField(max_length=16, choices=State.choices, default=State.UPLOADING)
    name = models.CharField(max_length=1024)
    mime_type = models.CharField(max_length=255, blank=True, default="")
    size = models.BigIntegerField(default=0)
    drive_file_id = models.CharField(max_length=255, blank=True, default="")
    web_view_link = models.URLField(max_length=2048, blank=True, default="")
    # Where the bytes go while uploading. It is a credential for writing this one
    # file, so it is never sent to anybody but the person uploading it.
    upload_session_url = models.TextField(blank=True, default="")
    uploaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "gdrive_files"
        verbose_name = "Google Drive file"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["issue", "state"])]

    @property
    def is_image(self):
        return self.mime_type.startswith("image/")
