/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useState } from "react";
import { observer } from "mobx-react";
import type { FileRejection } from "react-dropzone";
import { useDropzone } from "react-dropzone";
import { UploadOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import { setToast } from "@plane/blocks/toast";
import type { TIssueServiceType } from "@plane/types";
import { EIssueServiceType } from "@plane/types";
import { cn } from "@plane/utils";
// components
import { DriveAttachmentList, PlaneAttachmentsHeader } from "@/components/google-drive/drive-attachment-list";
import { attachFilesToDrive, useDriveIssue } from "@/components/google-drive/drive-issue";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// plane web hooks
import { useFileSize } from "@/hooks/use-file-size";
// types
import type { TAttachmentHelpers } from "../issue-detail-widgets/attachments/helper";
// components
import { IssueAttachmentsListItem } from "./attachment-list-item";
import { IssueAttachmentsUploadItem } from "./attachment-list-upload-item";
// types
import { IssueAttachmentDeleteModal } from "./delete-attachment-modal";

type TIssueAttachmentItemList = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  attachmentHelpers: TAttachmentHelpers;
  disabled?: boolean;
  issueServiceType?: TIssueServiceType;
};

export const IssueAttachmentItemList = observer(function IssueAttachmentItemList(props: TIssueAttachmentItemList) {
  const {
    workspaceSlug,
    projectId,
    issueId,
    attachmentHelpers,
    disabled,
    issueServiceType = EIssueServiceType.ISSUES,
  } = props;
  const { t } = useTranslation();
  // states
  const [isUploading, setIsUploading] = useState(false);
  // store hooks
  const {
    attachment: { getAttachmentsByIssueId },
    attachmentDeleteModalId,
    toggleDeleteAttachmentModal,
    fetchActivities,
  } = useIssueDetail(issueServiceType);
  const { operations: attachmentOperations, snapshot: attachmentSnapshot } = attachmentHelpers;
  const { create: createAttachment } = attachmentOperations;
  const { uploadStatus } = attachmentSnapshot;
  // file size
  const { maxFileSize } = useFileSize();
  // derived values
  const issueAttachments = getAttachmentsByIssueId(issueId);
  // A project with a Google Drive folder keeps its files there, with no limit on size or number.
  const { data: drive } = useDriveIssue(workspaceSlug, projectId, issueId);
  const toDrive = Boolean(drive?.enabled);

  // handlers
  const handleFetchPropertyActivities = useCallback(() => {
    fetchActivities(workspaceSlug, projectId, issueId);
  }, [fetchActivities, workspaceSlug, projectId, issueId]);

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
      if (toDrive) {
        if (acceptedFiles.length) void attachFilesToDrive(acceptedFiles, { workspaceSlug, projectId, issueId }, t);
        return;
      }
      const totalAttachedFiles = acceptedFiles.length + rejectedFiles.length;

      if (rejectedFiles.length === 0) {
        const currentFile: File = acceptedFiles[0];
        if (!currentFile || !workspaceSlug) return;

        setIsUploading(true);
        createAttachment(currentFile)
          // useAttachmentOperations has already said why the upload failed
          .catch(() => undefined)
          .finally(() => {
            handleFetchPropertyActivities();
            setIsUploading(false);
          });
        return;
      }

      setToast({
        type: "error",
        title: t("toast.error"),
        message:
          totalAttachedFiles > 1
            ? t("attachment.only_one_file_allowed")
            : t("attachment.file_size_limit", { size: maxFileSize / 1024 / 1024 }),
      });
      return;
    },
    [toDrive, projectId, issueId, createAttachment, maxFileSize, workspaceSlug, handleFetchPropertyActivities, t]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxSize: toDrive ? undefined : maxFileSize,
    multiple: toDrive,
    disabled: isUploading || disabled,
    // With Drive the list is for opening and removing files, and Attach is the way to add one:
    // a click anywhere on it, even in a dialog it opened, must not ask for files.
    noClick: toDrive,
    noKeyboard: toDrive,
  });

  const dropOverlay = isDragActive && (
    <div className="absolute top-0 left-0 z-30 flex h-full w-full items-center justify-center bg-surface-2/75">
      <div className="flex items-center justify-center rounded-md bg-surface-1 p-1">
        <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-strong px-5 py-6">
          <UploadOutline className="size-7" />
          <span className="text-13 text-tertiary">
            {toDrive ? t("google_drive_integration.attachments.drop_here") : t("attachment.drag_and_drop")}
          </span>
        </div>
      </div>
    </div>
  );

  const deleteModal = attachmentDeleteModalId && (
    <IssueAttachmentDeleteModal
      isOpen={Boolean(attachmentDeleteModalId)}
      onClose={() => toggleDeleteAttachmentModal(null)}
      attachmentOperations={attachmentOperations}
      attachmentId={attachmentDeleteModalId}
      issueServiceType={issueServiceType}
    />
  );

  const planeAttachments = issueAttachments?.map((attachmentId) => (
    <IssueAttachmentsListItem
      key={attachmentId}
      attachmentId={attachmentId}
      disabled={disabled}
      issueServiceType={issueServiceType}
    />
  ));

  // One drop area for the whole list: the files in Drive first, then any from before the folder.
  if (toDrive)
    return (
      <>
        {deleteModal}
        <div
          {...getRootProps()}
          className={cn("relative flex flex-col", { "min-h-[200px]": isDragActive && !issueAttachments?.length })}
        >
          <input {...getInputProps()} />
          {dropOverlay}
          <DriveAttachmentList
            workspaceSlug={workspaceSlug}
            projectId={projectId}
            issueId={issueId}
            disabled={disabled}
          />
          {!!issueAttachments?.length && (
            <>
              <PlaneAttachmentsHeader
                workspaceSlug={workspaceSlug}
                projectId={projectId}
                issueId={issueId}
                issueServiceType={issueServiceType}
                disabled={disabled}
              />
              {planeAttachments}
            </>
          )}
        </div>
      </>
    );

  return (
    <>
      {uploadStatus?.map((fileStatus) => (
        <IssueAttachmentsUploadItem key={fileStatus.id} uploadStatus={fileStatus} />
      ))}
      {issueAttachments && (
        <>
          {deleteModal}
          <div
            {...getRootProps()}
            className={cn("relative flex flex-col", disabled ? "cursor-not-allowed" : "cursor-pointer", {
              "min-h-[200px]": isDragActive && issueAttachments.length < 3,
            })}
          >
            <input {...getInputProps()} />
            {dropOverlay}
            {planeAttachments}
          </div>
        </>
      )}
    </>
  );
});
