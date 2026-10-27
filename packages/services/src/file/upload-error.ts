/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import axios from "axios";

/**
 * The steps of an upload, each of which fails in its own way: Plane is asked for an
 * upload link ("prepare"), the file goes straight to the storage server ("upload"),
 * and Plane is told the upload finished ("confirm").
 */
export type TFileUploadStage = "prepare" | "upload" | "confirm";

/** Why an upload failed, in terms a person can act on. */
export enum EFileUploadErrorCode {
  CANCELLED = "cancelled",
  STORAGE_FULL = "storage_full",
  FILE_TOO_LARGE = "file_too_large",
  FILE_TYPE_NOT_ALLOWED = "file_type_not_allowed",
  NETWORK = "network",
  LINK_EXPIRED = "link_expired",
  NOT_ALLOWED = "not_allowed",
  STORAGE_REJECTED = "storage_rejected",
  STORAGE_UNAVAILABLE = "storage_unavailable",
  SERVER_ERROR = "server_error",
  NOT_STORED = "not_stored",
  NOT_SAVED = "not_saved",
  UNKNOWN = "unknown",
}

export class FileUploadError extends Error {
  readonly code: EFileUploadErrorCode;
  readonly stage: TFileUploadStage;
  /** The HTTP status, when there was a response */
  readonly status?: number;
  /** What the server said, for the console and bug reports */
  readonly detail?: string;
  /** The largest file accepted, in bytes, when the server said */
  readonly limit?: number;

  constructor(
    code: EFileUploadErrorCode,
    stage: TFileUploadStage,
    { status, detail, limit, cause }: { status?: number; detail?: string; limit?: number; cause?: unknown } = {}
  ) {
    super(`File upload failed at ${stage}: ${code}${status ? ` (HTTP ${status})` : ""}${detail ? `: ${detail}` : ""}`, {
      cause,
    });
    this.name = "FileUploadError";
    this.code = code;
    this.stage = stage;
    this.status = status;
    this.detail = detail;
    this.limit = limit;
  }
}

export const isFileUploadError = (error: unknown): error is FileUploadError => error instanceof FileUploadError;

/** The FileUploadError behind an error, which callers often wrap in an Error of their own as its cause. */
export const findFileUploadError = (error: unknown): FileUploadError | undefined => {
  let current = error;
  for (let depth = 0; current && depth < 5; depth++) {
    if (isFileUploadError(current)) return current;
    current = (current as { cause?: unknown }).cause;
  }
  return undefined;
};

/** Whether the person stopped the upload themselves, which needs no message. */
export const isFileUploadCancelled = (error: unknown): boolean =>
  findFileUploadError(error)?.code === EFileUploadErrorCode.CANCELLED;

// Storage servers (MinIO, S3) answer in XML: <Error><Code>…</Code><Message>…</Message></Error>
const xmlField = (body: string, field: string): string | undefined =>
  new RegExp(`<${field}>([^<]*)</${field}>`).exec(body)?.[1];

/**
 * Turn whatever an upload step threw into a FileUploadError that says why.
 *
 * The storage step talks to the storage server directly, so its reason is in an XML
 * body; Plane's own steps answer in JSON, with a `code` where the API gives one.
 */
export const toFileUploadError = (error: unknown, stage: TFileUploadStage): FileUploadError => {
  if (isFileUploadError(error)) return error;
  // oxlint-disable-next-line import/no-named-as-default-member -- isCancel is accessed via the default export at runtime
  if (axios.isCancel(error)) return new FileUploadError(EFileUploadErrorCode.CANCELLED, stage, { cause: error });

  // Not a request that failed, but a fault of our own along the way
  // oxlint-disable-next-line import/no-named-as-default-member -- isAxiosError is accessed via the default export at runtime
  if (!axios.isAxiosError(error)) return new FileUploadError(EFileUploadErrorCode.UNKNOWN, stage, { cause: error });
  const response = error.response;
  // No response at all: offline, a dropped connection, DNS, or a proxy that cut the request
  if (!response) return new FileUploadError(EFileUploadErrorCode.NETWORK, stage, { cause: error });

  const status = response.status;
  const body = response.data;
  const xml = typeof body === "string" ? body : "";
  const json = body && typeof body === "object" ? (body as { code?: unknown; error?: unknown; limit?: unknown }) : {};
  const storageCode = xmlField(xml, "Code");
  const apiCode = typeof json.code === "string" ? json.code : undefined;
  const detail = (typeof json.error === "string" ? json.error : undefined) ?? xmlField(xml, "Message");
  const limit = typeof json.limit === "number" ? json.limit : undefined;
  const fail = (code: EFileUploadErrorCode) =>
    new FileUploadError(code, stage, { status, detail, limit, cause: error });

  if (status === 507 || /StorageFull/i.test(storageCode ?? "")) return fail(EFileUploadErrorCode.STORAGE_FULL);
  if (status === 413 || storageCode === "EntityTooLarge" || apiCode === "FILE_TOO_LARGE")
    return fail(EFileUploadErrorCode.FILE_TOO_LARGE);
  if (apiCode === "FILE_TYPE_NOT_ALLOWED" || (stage === "prepare" && status === 400 && /file type/i.test(detail ?? "")))
    return fail(EFileUploadErrorCode.FILE_TYPE_NOT_ALLOWED);
  if (apiCode === "UPLOAD_NOT_FOUND") return fail(EFileUploadErrorCode.NOT_STORED);
  if (
    storageCode === "ExpiredToken" ||
    storageCode === "RequestTimeTooSkewed" ||
    (storageCode === "AccessDenied" && /expired/i.test(detail ?? ""))
  )
    return fail(EFileUploadErrorCode.LINK_EXPIRED);
  if (status === 401 || status === 403)
    return fail(stage === "upload" ? EFileUploadErrorCode.STORAGE_REJECTED : EFileUploadErrorCode.NOT_ALLOWED);
  if (status !== undefined && status >= 500)
    return fail(stage === "upload" ? EFileUploadErrorCode.STORAGE_UNAVAILABLE : EFileUploadErrorCode.SERVER_ERROR);
  if (stage === "confirm") return fail(EFileUploadErrorCode.NOT_SAVED);
  return fail(EFileUploadErrorCode.UNKNOWN);
};

const CONFIRM_ATTEMPTS = 3;

/**
 * Tell Plane an upload finished, trying again when the request itself fails.
 *
 * By now the file is in storage, so giving up on a dropped connection or a busy
 * server would report a stored file as failed. An answer that will not change
 * (the file is not there, no permission) is not retried.
 */
export const confirmFileUpload = async <T>(confirm: () => Promise<T>, retryDelayMs = 1000, attempt = 1): Promise<T> => {
  try {
    return await confirm();
  } catch (error) {
    const uploadError = toFileUploadError(error, "confirm");
    const retryable =
      uploadError.code === EFileUploadErrorCode.NETWORK || uploadError.code === EFileUploadErrorCode.SERVER_ERROR;
    if (!retryable) throw uploadError;
    if (attempt >= CONFIRM_ATTEMPTS)
      // The file is in storage; what keeps failing is telling Plane so
      throw new FileUploadError(EFileUploadErrorCode.NOT_SAVED, "confirm", {
        status: uploadError.status,
        detail: uploadError.detail,
        cause: error,
      });
    await new Promise((resolve) => setTimeout(resolve, retryDelayMs * attempt));
    return confirmFileUpload(confirm, retryDelayMs, attempt + 1);
  }
};

export type TFileUploadErrorMessage = {
  /** i18n key of a short headline */
  title: string;
  /** i18n key of a sentence that says what happened and what to do */
  description: string;
  params?: Record<string, string>;
};

const formatMegabytes = (bytes: number): string => `${Number((bytes / (1024 * 1024)).toFixed(1))} MB`;

/** The i18n keys that explain an upload failure to the person who tried it. */
export const getFileUploadErrorMessage = (error: unknown): TFileUploadErrorMessage => {
  const uploadError = findFileUploadError(error);
  const key = `file_upload.errors.${uploadError?.code ?? EFileUploadErrorCode.UNKNOWN}`;
  if (uploadError?.code === EFileUploadErrorCode.FILE_TOO_LARGE && uploadError.limit)
    return {
      title: `${key}.title`,
      description: `${key}.description_with_limit`,
      params: { limit: formatMegabytes(uploadError.limit) },
    };
  return { title: `${key}.title`, description: `${key}.description` };
};
