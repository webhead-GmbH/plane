/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { MAX_FILE_SIZE } from "@plane/constants";
import type { TFileHandler } from "@plane/editor";
import type { TTranslationStore } from "@plane/i18n";
import { SitesFileService } from "@plane/services";
import { getFileURL } from "@plane/utils";
// helpers
import { describeFileUploadError, showFileUploadError, showUnsupportedEditorFiles } from "./file-upload-error.helper";
// services
const sitesFileService = new SitesFileService();

/**
 * @description generate the file source using assetId
 * @param {string} anchor
 */
export const getEditorAssetSrc = (anchor: string, assetId: string): string | undefined => {
  const url = getFileURL(`/api/public/assets/v2/anchor/${anchor}/${assetId}/`);
  return url;
};

type TArgs = {
  anchor: string;
  t: TTranslationStore["t"];
  uploadFile: TFileHandler["upload"];
  workspaceId: string;
};

/**
 * @description this function returns the file handler required by the editors
 * @param {TArgs} args
 */
export const getEditorFileHandlers = (args: TArgs): TFileHandler => {
  const { anchor, t, uploadFile, workspaceId } = args;

  const getAssetSrc = async (path: string) => {
    if (!path) return "";
    if (path?.startsWith("http")) {
      return path;
    } else {
      return getEditorAssetSrc(anchor, path) ?? "";
    }
  };

  return {
    checkIfAssetExists: async () => true,
    assetsUploadStatus: {},
    getAssetDownloadSrc: getAssetSrc,
    getAssetSrc: getAssetSrc,
    upload: async (blockId, file) => {
      try {
        return await uploadFile(blockId, file);
      } catch (error) {
        showFileUploadError(t, error);
        // The editor shows this next to the image, with a way to try again
        throw new Error(describeFileUploadError(t, error).message, { cause: error });
      }
    },
    onUnsupportedFiles: (files) => showUnsupportedEditorFiles(t, files),
    delete: async (src: string) => {
      if (src?.startsWith("http")) {
        await sitesFileService.deleteOldEditorAsset(workspaceId, src);
      } else {
        await sitesFileService.deleteNewAsset(getEditorAssetSrc(anchor, src) ?? "");
      }
    },
    cancel: sitesFileService.cancelUpload,
    restore: async (src: string) => {
      if (src?.startsWith("http")) {
        await sitesFileService.restoreOldEditorAsset(workspaceId, src);
      } else {
        await sitesFileService.restoreNewAsset(anchor, src);
      }
    },
    duplicate: async (assetId: string) =>
      // Duplication is not supported for sites/space app
      // Return the same assetId as a fallback
      assetId,
    validation: {
      maxFileSize: MAX_FILE_SIZE,
    },
  };
};
