/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AxiosError, AxiosHeaders, CanceledError } from "axios";
import type { InternalAxiosRequestConfig } from "axios";
import { describe, expect, it } from "vitest";
import {
  confirmFileUpload,
  EFileUploadErrorCode,
  FileUploadError,
  getFileUploadErrorMessage,
  toFileUploadError,
} from "./upload-error";

const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;

const answered = (status: number, data: unknown) =>
  new AxiosError(
    "Request failed",
    "ERR_BAD_RESPONSE",
    config,
    {},
    { status, statusText: "", headers: {}, config, data }
  );

// What the live storage server answered when its disk was full
const MINIO_FULL = `<?xml version="1.0" encoding="UTF-8"?>
<Error><Code>XMinioStorageFull</Code><Message>Storage backend has reached its minimum free drive threshold. Please delete a few objects to proceed.</Message><Key>a/b.png</Key><BucketName>uploads</BucketName></Error>`;

const s3Error = (code: string, message: string) =>
  `<?xml version="1.0" encoding="UTF-8"?><Error><Code>${code}</Code><Message>${message}</Message></Error>`;

describe("toFileUploadError", () => {
  it.each([
    ["a full storage server", answered(507, MINIO_FULL), "upload", EFileUploadErrorCode.STORAGE_FULL],
    [
      "a file the proxy found too large",
      answered(413, "<html>413</html>"),
      "upload",
      EFileUploadErrorCode.FILE_TOO_LARGE,
    ],
    [
      "a file larger than the signed upload allows",
      answered(400, s3Error("EntityTooLarge", "Your proposed upload exceeds the maximum allowed object size.")),
      "upload",
      EFileUploadErrorCode.FILE_TOO_LARGE,
    ],
    [
      "a file Plane refuses as too large",
      answered(400, { error: "The file is too large.", code: "FILE_TOO_LARGE", limit: 5242880 }),
      "prepare",
      EFileUploadErrorCode.FILE_TOO_LARGE,
    ],
    [
      "a file type Plane refuses",
      answered(400, { error: "Invalid file type.", code: "FILE_TYPE_NOT_ALLOWED" }),
      "prepare",
      EFileUploadErrorCode.FILE_TYPE_NOT_ALLOWED,
    ],
    [
      "an image type refused by an older server",
      answered(400, { error: "Invalid file type. Only JPEG, PNG, WebP, JPG and GIF files are allowed." }),
      "prepare",
      EFileUploadErrorCode.FILE_TYPE_NOT_ALLOWED,
    ],
    [
      "an expired upload link",
      answered(403, s3Error("AccessDenied", "Invalid according to Policy: Policy expired.")),
      "upload",
      EFileUploadErrorCode.LINK_EXPIRED,
    ],
    [
      "any other refusal by storage",
      answered(403, s3Error("AccessDenied", "Access Denied.")),
      "upload",
      EFileUploadErrorCode.STORAGE_REJECTED,
    ],
    ["a refusal by Plane", answered(403, { error: "No access" }), "prepare", EFileUploadErrorCode.NOT_ALLOWED],
    ["storage that is down", answered(502, "Bad Gateway"), "upload", EFileUploadErrorCode.STORAGE_UNAVAILABLE],
    ["Plane failing", answered(500, "Server Error"), "prepare", EFileUploadErrorCode.SERVER_ERROR],
    [
      "a confirmation of a file storage never got",
      answered(400, { error: "The file is not in storage.", code: "UPLOAD_NOT_FOUND" }),
      "confirm",
      EFileUploadErrorCode.NOT_STORED,
    ],
    ["another failed confirmation", answered(409, {}), "confirm", EFileUploadErrorCode.NOT_SAVED],
    ["anything else", answered(418, {}), "prepare", EFileUploadErrorCode.UNKNOWN],
  ] as const)("names %s", (_, error, stage, code) => {
    expect(toFileUploadError(error, stage).code).toBe(code);
  });

  it("names a request that got no answer a network failure", () => {
    const error = new AxiosError("Network Error", "ERR_NETWORK", config, {});
    expect(toFileUploadError(error, "upload").code).toBe(EFileUploadErrorCode.NETWORK);
  });

  it("does not mistake a fault of our own for the network", () => {
    expect(toFileUploadError(new TypeError("x is undefined"), "prepare").code).toBe(EFileUploadErrorCode.UNKNOWN);
  });

  it("knows a cancelled upload", () => {
    expect(toFileUploadError(new CanceledError("Upload canceled"), "upload").code).toBe(EFileUploadErrorCode.CANCELLED);
  });

  it("keeps what storage and Plane said", () => {
    const full = toFileUploadError(answered(507, MINIO_FULL), "upload");
    expect(full.status).toBe(507);
    expect(full.detail).toContain("minimum free drive threshold");

    const large = toFileUploadError(answered(400, { code: "FILE_TOO_LARGE", limit: 5242880 }), "prepare");
    expect(large.limit).toBe(5242880);
  });

  it("passes an already named failure through unchanged, whatever the later step", () => {
    const failure = toFileUploadError(answered(507, MINIO_FULL), "upload");
    expect(toFileUploadError(failure, "prepare")).toBe(failure);
  });
});

describe("confirmFileUpload", () => {
  it("tries again when the request is lost, since the file is already stored", async () => {
    let calls = 0;
    const result = await confirmFileUpload(async () => {
      calls += 1;
      if (calls < 3) throw new AxiosError("Network Error", "ERR_NETWORK", config, {});
      return "done";
    }, 0);
    expect(result).toBe("done");
    expect(calls).toBe(3);
  });

  it("gives up after three attempts and says the file arrived but was not recorded", async () => {
    let calls = 0;
    const attempt = confirmFileUpload(async () => {
      calls += 1;
      throw answered(503, "busy");
    }, 0);
    await expect(attempt).rejects.toMatchObject({
      code: EFileUploadErrorCode.NOT_SAVED,
      stage: "confirm",
      status: 503,
    });
    expect(calls).toBe(3);
  });

  it("does not repeat an answer that will not change", async () => {
    let calls = 0;
    const attempt = confirmFileUpload(async () => {
      calls += 1;
      throw answered(400, { code: "UPLOAD_NOT_FOUND" });
    }, 0);
    await expect(attempt).rejects.toMatchObject({ code: EFileUploadErrorCode.NOT_STORED });
    expect(calls).toBe(1);
  });
});

describe("getFileUploadErrorMessage", () => {
  it("points at the keys for the failure", () => {
    const message = getFileUploadErrorMessage(toFileUploadError(answered(507, MINIO_FULL), "upload"));
    expect(message).toEqual({
      title: "file_upload.errors.storage_full.title",
      description: "file_upload.errors.storage_full.description",
    });
  });

  it("gives the size limit in megabytes when the server said it", () => {
    const message = getFileUploadErrorMessage(
      new FileUploadError(EFileUploadErrorCode.FILE_TOO_LARGE, "prepare", { limit: 5242880 })
    );
    expect(message.description).toBe("file_upload.errors.file_too_large.description_with_limit");
    expect(message.params).toEqual({ limit: "5 MB" });
  });

  it("finds the failure inside an error that wraps it", () => {
    const failure = toFileUploadError(answered(507, MINIO_FULL), "upload");
    const wrapped = new Error("Asset upload failed. Please try again later.", { cause: failure });
    expect(getFileUploadErrorMessage(wrapped).title).toBe("file_upload.errors.storage_full.title");
  });

  it("falls back to an unknown failure for anything else", () => {
    expect(getFileUploadErrorMessage(undefined).title).toBe("file_upload.errors.unknown.title");
  });
});
