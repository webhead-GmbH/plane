/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { ExternalLink, FolderOpen } from "lucide-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Dialog, DialogContent, DialogTitle } from "@makeplane/propel/components/dialog";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { DeleteOutline, MoreHorizontalOutline } from "@makeplane/propel/icons";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { convertBytesToSize, getFileExtension, renderFormattedDate } from "@plane/utils";
// components
import { ButtonAvatars } from "@/components/dropdowns/member/avatar";
import { getFileIcon } from "@/components/icons";
import { IssueAttachmentsUploadItem } from "@/components/issues/attachment/attachment-list-upload-item";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { usePlatformOS } from "@/hooks/use-platform-os";
// services
import { GoogleDriveService } from "@/services/google-drive.service";
import type { TDriveFile } from "@/services/google-drive.service";
// local imports
import { driveUploads, refreshDriveIssue, useDriveIssue } from "./drive-issue";
import { I18N, driveErrorMessage } from "./errors";

const driveService = new GoogleDriveService();

type TProps = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
};

/** The work item's files in Google Drive, with the ones still on their way at the top. */
export const DriveAttachmentList = observer(function DriveAttachmentList(props: TProps) {
  const { workspaceSlug, projectId, issueId, disabled } = props;
  const { t } = useTranslation();
  const { data } = useDriveIssue(workspaceSlug, projectId, issueId);
  const [previewing, setPreviewing] = useState<TDriveFile | null>(null);
  const [removing, setRemoving] = useState<TDriveFile | null>(null);
  const [isRemoving, setIsRemoving] = useState(false);
  const uploads = driveUploads.get(issueId) ?? [];

  if (!data?.enabled) return null;

  const handleRemove = async () => {
    if (!removing) return;
    setIsRemoving(true);
    try {
      await driveService.removeFile(workspaceSlug, projectId, issueId, removing.id);
      await refreshDriveIssue(workspaceSlug, projectId, issueId);
      setRemoving(null);
    } catch (failure) {
      setToast({
        type: "error",
        title: t(`${I18N}.attachments.remove_failed`),
        message: driveErrorMessage(failure, t),
      });
    } finally {
      setIsRemoving(false);
    }
  };

  return (
    <div className="flex flex-col">
      {/* Where the files are, so nobody wonders why they cannot be found on the server. */}
      <div className="flex items-center justify-between gap-3 px-3 py-1.5 text-12 text-tertiary">
        <span className="inline-flex items-center gap-1.5">
          <FolderOpen className="size-3.5" aria-hidden />
          {t(`${I18N}.attachments.in_drive`)}
        </span>
        {data.folder_url && (
          <a
            href={data.folder_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-secondary hover:text-primary hover:underline"
            onClick={(event) => event.stopPropagation()}
          >
            {t(`${I18N}.attachments.open_folder`)}
            <ExternalLink className="size-3" aria-hidden />
          </a>
        )}
      </div>

      {uploads.map((upload) => (
        <IssueAttachmentsUploadItem key={upload.id} uploadStatus={upload} />
      ))}

      {data.files.map((file) => (
        <DriveAttachmentRow
          key={file.id}
          workspaceSlug={workspaceSlug}
          file={file}
          disabled={disabled}
          onPreview={() => setPreviewing(file)}
          onRemove={() => setRemoving(file)}
        />
      ))}

      <DrivePreviewDialog workspaceSlug={workspaceSlug} file={previewing} onClose={() => setPreviewing(null)} />
      <ConfirmDialog
        isOpen={removing !== null}
        handleClose={() => setRemoving(null)}
        handleSubmit={() => void handleRemove()}
        isSubmitting={isRemoving}
        variant="danger"
        title={t(`${I18N}.attachments.remove_title`)}
        content={t(`${I18N}.attachments.remove_body`, { name: removing?.name ?? "" })}
        primaryButtonText={{ default: t(`${I18N}.attachments.remove`), loading: t(`${I18N}.attachments.removing`) }}
        secondaryButtonText={t("common.cancel")}
      />
    </div>
  );
});

type TRowProps = {
  workspaceSlug: string;
  file: TDriveFile;
  disabled?: boolean;
  onPreview: () => void;
  onRemove: () => void;
};

const DriveAttachmentRow = observer(function DriveAttachmentRow(props: TRowProps) {
  const { workspaceSlug, file, disabled, onPreview, onRemove } = props;
  const { t } = useTranslation();
  const { getUserDetails } = useMember();
  const { isMobile } = usePlatformOS();
  const uploader = file.created_by ? getUserDetails(file.created_by) : undefined;

  return (
    <div className="group flex h-11 items-center hover:bg-surface-2">
      {/* An image opens a preview here; anything else opens in Drive, which can show it. */}
      <button
        type="button"
        className="flex h-full min-w-0 flex-1 items-center gap-3 truncate pl-3 text-left text-13"
        onClick={(event) => {
          event.stopPropagation();
          if (file.is_image) onPreview();
          else window.open(file.web_view_link, "_blank", "noopener,noreferrer");
        }}
      >
        {file.is_image ? (
          <img
            src={driveService.previewUrl(workspaceSlug, file.id, 200)}
            alt=""
            loading="lazy"
            className="size-7 shrink-0 rounded-sm border border-subtle object-cover"
          />
        ) : (
          <span className="flex items-center">{getFileIcon(getFileExtension(file.name), 18)}</span>
        )}
        <Tooltip label={file.name} layout="stacked" disabled={isMobile}>
          <span className="truncate font-medium text-secondary">{file.name}</span>
        </Tooltip>
        <span className="flex size-1.5 shrink-0 rounded-full bg-layer-1" />
        <span className="shrink-0 text-placeholder">{convertBytesToSize(file.size)}</span>
      </button>

      <div
        role="presentation"
        className="flex h-full items-center gap-3 px-3"
        onClick={(event) => event.stopPropagation()}
      >
        {file.created_by && (
          <Tooltip
            label={t(`${I18N}.attachments.uploaded_by`, {
              name: uploader?.display_name ?? "",
              date: renderFormattedDate(file.created_at),
            })}
            layout="stacked"
            disabled={isMobile}
          >
            <div className="flex items-center justify-center">
              <ButtonAvatars showTooltip userIds={file.created_by} />
            </div>
          </Tooltip>
        )}
        <Menu>
          <MenuTrigger
            render={
              <IconButton
                variant="ghost"
                size="sm"
                aria-label={t("aria_labels.common.more_actions")}
                icon={<Icon icon={MoreHorizontalOutline} />}
              />
            }
          />
          <MenuContent side="bottom" align="end">
            <MenuItem
              icon={<Icon icon={ExternalLink} />}
              label={t(`${I18N}.attachments.open_in_drive`)}
              onClick={() => window.open(file.web_view_link, "_blank", "noopener,noreferrer")}
            />
            {!disabled && (
              <MenuItem
                icon={<Icon icon={DeleteOutline} />}
                label={t(`${I18N}.attachments.remove`)}
                onClick={onRemove}
              />
            )}
          </MenuContent>
        </Menu>
      </div>
    </div>
  );
});

type TPreviewProps = { workspaceSlug: string; file: TDriveFile | null; onClose: () => void };

/** A large view of an image, without leaving the work item. */
const DrivePreviewDialog = ({ workspaceSlug, file, onClose }: TPreviewProps) => {
  const { t } = useTranslation();
  return (
    <Dialog open={file !== null} onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent size="xl">
        {file && (
          <div className="flex max-h-[90vh] flex-col gap-3 p-4">
            <DialogTitle>
              <span className="block truncate">{file.name}</span>
            </DialogTitle>
            <div className="flex min-h-48 grow items-center justify-center overflow-hidden rounded-md bg-layer-1">
              <img
                src={driveService.previewUrl(workspaceSlug, file.id, 1600)}
                alt={file.name}
                className="max-h-[70vh] max-w-full object-contain"
              />
            </div>
            <div className="flex items-center justify-end gap-2">
              <Button
                variant="secondary"
                size="md"
                stretch="auto"
                label={t(`${I18N}.attachments.close`)}
                onClick={onClose}
              />
              <Button
                variant="primary"
                size="md"
                stretch="auto"
                label={t(`${I18N}.attachments.open_in_drive`)}
                onClick={() => window.open(file.web_view_link, "_blank", "noopener,noreferrer")}
              />
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
