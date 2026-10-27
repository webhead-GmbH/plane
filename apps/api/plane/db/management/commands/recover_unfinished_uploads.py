# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.core.management import BaseCommand, CommandError
from django.db.models import Q

# Module imports
from plane.db.models import FileAsset
from plane.settings.storage import PROBE_CLIENT_CONFIG, S3Storage, StorageUnavailable


class Command(BaseCommand):
    help = (
        "Make reachable again the files that are in storage although their upload was never "
        "recorded as finished, which hid them from the attachment list and from downloads. "
        "With --include-deleted, also brings back the records of such files that the nightly "
        "cleanup removed before it checked storage. Records that a person deleted, and records "
        "of deleted work items, pages, comments, projects or workspaces, are left alone."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="List what would change without changing it")
        parser.add_argument(
            "--include-deleted",
            action="store_true",
            help="Also bring back records removed by the cleanup of unfinished uploads",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        assets = FileAsset.all_objects.filter(is_uploaded=False)
        if options["include_deleted"]:
            # is_deleted is set only when a person deletes an asset; the cleanup never set it
            assets = assets.filter(is_deleted=False).exclude(
                Q(workspace__deleted_at__isnull=False)
                | Q(project__deleted_at__isnull=False)
                | Q(issue__deleted_at__isnull=False)
                | Q(page__deleted_at__isnull=False)
                | Q(comment__deleted_at__isnull=False)
                | Q(draft_issue__deleted_at__isnull=False)
            )
        else:
            assets = assets.filter(deleted_at__isnull=True)

        storage = S3Storage(client_config=PROBE_CLIENT_CONFIG)
        recovered = missing = 0
        for asset in assets.order_by("created_at").iterator():
            try:
                metadata = storage.find_object(asset.asset.name)
            except StorageUnavailable as e:
                raise CommandError(f"Storage cannot be reached, nothing more was checked: {e}") from e
            if metadata is None:
                missing += 1
                continue

            recovered += 1
            restored = " (its record had been removed)" if asset.deleted_at else ""
            self.stdout.write(
                f"{'Would recover' if dry_run else 'Recovered'} {asset.id} {asset.entity_type} "
                f"{asset.attributes.get('name', '')!r}, uploaded {asset.created_at:%Y-%m-%d}{restored}"
            )
            if dry_run:
                continue
            fields = ["is_uploaded", "storage_metadata"]
            asset.is_uploaded = True
            asset.storage_metadata = metadata
            if asset.deleted_at:
                asset.deleted_at = None
                fields.append("deleted_at")
            asset.save(update_fields=fields, disable_auto_set_user=True)

        verb = "would be recovered" if dry_run else "recovered"
        self.stdout.write(
            self.style.SUCCESS(
                f"{recovered} file(s) {verb}; {missing} unfinished upload(s) have no file in storage and stay hidden."
            )
        )
