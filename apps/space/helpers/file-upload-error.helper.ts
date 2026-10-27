/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { setToast } from "@plane/blocks/toast";
import type { TTranslationStore } from "@plane/i18n";
import { findFileUploadError, getFileUploadErrorMessage, isFileUploadCancelled } from "@plane/services";

type TTranslate = TTranslationStore["t"];

/** Why an upload failed and what to do about it, in the reader's language. */
export const describeFileUploadError = (t: TTranslate, error: unknown) => {
  const { title, description, params } = getFileUploadErrorMessage(error);
  return { title: t(title, params), message: t(description, params) };
};

/** Whether an error came from an upload, which showFileUploadError can explain. */
export const isFileUploadFailure = (error: unknown) => !!findFileUploadError(error);

/** Tell the person why their upload failed, unless they stopped it themselves. */
export const showFileUploadError = (t: TTranslate, error: unknown) => {
  if (isFileUploadCancelled(error)) return;
  console.error("File upload failed:", error);
  setToast({ type: "error", ...describeFileUploadError(t, error) });
};

/** Say which dropped or pasted files the editor could not add, since only images go into the text. */
export const showUnsupportedEditorFiles = (t: TTranslate, files: File[]) =>
  setToast({
    type: "error",
    title: t("file_upload.errors.not_an_image.title"),
    message: t("file_upload.errors.not_an_image.description", { names: files.map((file) => file.name).join(", ") }),
  });
