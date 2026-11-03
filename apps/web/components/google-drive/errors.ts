/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export const I18N = "google_drive_integration";

const KNOWN_CODES = new Set([
  "DRIVE_NOT_CONNECTED",
  "DRIVE_ACCESS_REVOKED",
  "DRIVE_PROJECT_NOT_LINKED",
  "DRIVE_NOT_FOUND",
  "DRIVE_NOT_A_FOLDER",
  "DRIVE_NO_PERMISSION",
  "DRIVE_STORAGE_FULL",
  "DRIVE_BAD_LINK",
  "DRIVE_CLIENT_MISSING",
  "DRIVE_EMPTY_FILE",
  "DRIVE_INCOMPLETE",
]);

/** The sentence for a Drive failure in the reader's language, from the code the server sent. */
export const driveErrorMessage = (failure: unknown, t: (key: string, values?: Record<string, unknown>) => string) => {
  const code = (failure as { code?: string } | undefined)?.code;
  return t(`${I18N}.errors.${code && KNOWN_CODES.has(code) ? code : "DRIVE_ERROR"}`);
};
