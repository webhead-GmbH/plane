/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback } from "react";
// plane imports
import { setToast } from "@plane/blocks/toast";
import { API_BASE_URL } from "@plane/constants";
import type { TFileHandler } from "@plane/editor";
import { useTranslation } from "@plane/i18n";
import { getEditorAssetDownloadSrc, getEditorAssetSrc } from "@plane/utils";
// components
import { driveErrorMessage } from "@/components/google-drive/errors";
import { uploadFileToDrive } from "@/components/google-drive/upload";
import type { TDriveUploadTarget } from "@/components/google-drive/upload";
// helpers
import {
  describeFileUploadError,
  showFileUploadError,
  showUnsupportedEditorFiles,
} from "@/helpers/file-upload-error.helper";
// hooks
import { useEditorAsset } from "@/hooks/store/use-editor-asset";
// plane web hooks
import { useExtendedEditorConfig } from "@/hooks/editor/use-extended-editor-config";
import { useFileSize } from "@/hooks/use-file-size";
// services
import { FileService } from "@/services/file.service";
import { GoogleDriveService } from "@/services/google-drive.service";
const fileService = new FileService();

type TArgs = {
  projectId?: string;
  uploadFile: TFileHandler["upload"];
  duplicateFile: TFileHandler["duplicate"];
  workspaceId: string;
  workspaceSlug: string;
  /** The work item whose Google Drive folder the files go to, when its project has one. */
  drive?: TDriveUploadTarget;
};

// What an image in Google Drive is stored as in the text: not an asset id, so
// nothing that copies, restores or deletes Plane's own assets acts on it.
const DRIVE_SRC = "gdrive-";
const driveFileId = (src?: string) => (src?.startsWith(DRIVE_SRC) ? src.slice(DRIVE_SRC.length) : null);
const driveService = new GoogleDriveService();

export const useEditorConfig = () => {
  // store hooks
  const { assetsUploadPercentage, trackEditorUpload } = useEditorAsset();
  // file size
  const { maxFileSize } = useFileSize();
  const { getExtendedEditorFileHandlers } = useExtendedEditorConfig();
  const { t } = useTranslation();

  const getEditorFileHandlers = useCallback(
    (args: TArgs): TFileHandler => {
      const { projectId, uploadFile, duplicateFile, workspaceId, workspaceSlug, drive } = args;
      const driveDownloadSrc = (fileId: string) =>
        `${API_BASE_URL}/api/workspaces/${workspaceSlug}/drive/files/${fileId}/open/`;

      return {
        assetsUploadStatus: assetsUploadPercentage,
        cancel: fileService.cancelUpload,
        checkIfAssetExists: async (assetId: string) => {
          if (driveFileId(assetId)) return true;
          const res = await fileService.checkIfAssetExists(workspaceSlug, assetId);
          return res?.exists ?? false;
        },
        delete: async (src: string) => {
          // A file in Drive stays there when it leaves the text; it is removed from its folder, not here.
          if (driveFileId(src)) return;
          if (src?.startsWith("http")) {
            await fileService.deleteOldWorkspaceAsset(workspaceId, src);
          } else {
            await fileService.deleteNewAsset(
              getEditorAssetSrc({
                assetId: src,
                projectId,
                workspaceSlug,
              }) ?? ""
            );
          }
        },
        getAssetDownloadSrc: async (path) => {
          if (!path) return "";
          const inDrive = driveFileId(path);
          if (inDrive) return driveDownloadSrc(inDrive);
          if (path?.startsWith("http")) {
            return path;
          } else {
            return (
              getEditorAssetDownloadSrc({
                assetId: path,
                projectId,
                workspaceSlug,
              }) ?? ""
            );
          }
        },
        getAssetSrc: async (path) => {
          if (!path) return "";
          const inDrive = driveFileId(path);
          if (inDrive) return driveService.previewUrl(workspaceSlug, inDrive, 1600);
          if (path?.startsWith("http")) {
            return path;
          } else {
            return (
              getEditorAssetSrc({
                assetId: path,
                projectId,
                workspaceSlug,
              }) ?? ""
            );
          }
        },
        restore: async (src: string) => {
          if (driveFileId(src)) return;
          if (src?.startsWith("http")) {
            await fileService.restoreOldEditorAsset(workspaceId, src);
          } else {
            await fileService.restoreNewAsset(workspaceSlug, src);
          }
        },
        upload: async (blockId, file) => {
          try {
            if (drive) {
              const uploaded = await trackEditorUpload(blockId, file, (onProgress) =>
                uploadFileToDrive(file, drive, { onProgress: (fraction) => onProgress(Math.round(fraction * 100)) })
              );
              return `${DRIVE_SRC}${uploaded.id}`;
            }
            return await uploadFile(blockId, file);
          } catch (error) {
            showFileUploadError(t, error);
            // The editor shows this next to the image, with a way to try again
            throw new Error(describeFileUploadError(t, error).message, { cause: error });
          }
        },
        onUnsupportedFiles: (files) => showUnsupportedEditorFiles(t, files),
        // Any other file goes to Drive too, and the text gets a link to it where it was dropped.
        uploadAttachment: drive
          ? async (file) => {
              try {
                const uploaded = await uploadFileToDrive(file, drive);
                return { name: uploaded.name, url: uploaded.web_view_link };
              } catch (error) {
                setToast({
                  type: "error",
                  title: t("google_drive_integration.attachments.upload_failed", { name: file.name }),
                  message: driveErrorMessage(error, t),
                });
                throw error;
              }
            }
          : undefined,
        // The same file twice in Drive is one file, referred to twice.
        duplicate: async (assetId) => (driveFileId(assetId) ? assetId : duplicateFile(assetId)),
        validation: {
          // Drive takes files of any size; the limit is the Plane server's.
          maxFileSize: drive ? Number.MAX_SAFE_INTEGER : maxFileSize,
        },
        ...getExtendedEditorFileHandlers({ projectId, workspaceSlug }),
      };
    },
    [assetsUploadPercentage, getExtendedEditorFileHandlers, maxFileSize, t, trackEditorUpload]
  );

  return {
    getEditorFileHandlers,
  };
};
