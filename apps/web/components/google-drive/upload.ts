/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { GoogleDriveService } from "@/services/google-drive.service";
import type { TDriveError, TDriveFile, TDriveFileSource, TDriveUploadAnswer } from "@/services/google-drive.service";

const driveService = new GoogleDriveService();

export type TDriveUploadTarget = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  source: TDriveFileSource;
};

export type TDriveUploadOptions = {
  /** From 0 to 1, as the bytes go. */
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
};

/** A failed upload, with the server's code when it gave one, so the screen can say why. */
export class DriveUploadError extends Error {
  code: string;

  constructor(message: string, code = "DRIVE_ERROR") {
    super(message);
    this.name = "DriveUploadError";
    this.code = code;
  }
}

const asUploadError = (failure: unknown) => {
  if (failure instanceof DriveUploadError) return failure;
  if (failure instanceof DOMException && failure.name === "AbortError") return failure;
  const body = failure as TDriveError | undefined;
  return new DriveUploadError(body?.error ?? "The file could not be sent to Google Drive.", body?.code);
};

type TDirectAnswer = { done: boolean; received: number };

/**
 * One chunk straight to Google's upload session.
 *
 * Rejects with "network" when the browser could not reach Google or Google would
 * not answer it across origins — the cue to send the rest through the server.
 */
const putDirect = (
  url: string,
  chunk: Blob,
  start: number,
  total: number,
  onLoaded: (loaded: number) => void,
  signal?: AbortSignal
) =>
  new Promise<TDirectAnswer>((resolve, reject) => {
    const request = new XMLHttpRequest();
    const end = start + chunk.size;
    request.open("PUT", url);
    request.setRequestHeader("Content-Range", `bytes ${start}-${end - 1}/${total}`);
    // One request, thrown away when it ends: handlers that go with it, nothing to remove.
    // oxlint-disable-next-line unicorn/prefer-add-event-listener
    request.upload.onprogress = (event) => onLoaded(event.loaded);
    // oxlint-disable-next-line unicorn/prefer-add-event-listener
    request.onload = () => {
      if (request.status === 200 || request.status === 201) return resolve({ done: true, received: total });
      if (request.status === 308) {
        // "bytes=0-1048575" when Google lets the browser read it; otherwise the chunk arrived whole.
        const range = request.getResponseHeader("Range");
        return resolve({ done: false, received: range ? Number(range.split("-")[1]) + 1 : end });
      }
      reject(new Error(`status ${request.status}`));
    };
    // oxlint-disable-next-line unicorn/prefer-add-event-listener
    request.onerror = () => reject(new Error("network"));
    // oxlint-disable-next-line unicorn/prefer-add-event-listener
    request.onabort = () => reject(new DOMException("The upload was stopped.", "AbortError"));
    signal?.addEventListener("abort", () => request.abort(), { once: true });
    request.send(chunk);
  });

/**
 * Send a file to the work item's folder in Google Drive and return it as recorded.
 *
 * The Plane server only opens the upload; the bytes go from the browser to Google
 * in pieces, so a large file never passes through or lands on the server. If
 * Google will not take them from the browser, the rest go through the server one
 * small piece at a time — still never stored there.
 */
export async function uploadFileToDrive(
  file: File,
  target: TDriveUploadTarget,
  options: TDriveUploadOptions = {}
): Promise<TDriveFile> {
  const { workspaceSlug, projectId, issueId, source } = target;
  const { onProgress, signal } = options;
  if (file.size === 0) throw new DriveUploadError("This file is empty.", "DRIVE_EMPTY_FILE");

  let uploadId: string | null = null;
  try {
    const session = await driveService.startUpload(workspaceSlug, projectId, issueId, {
      name: file.name,
      size: file.size,
      mime_type: file.type || "application/octet-stream",
      source,
    });
    uploadId = session.file.id;
    const openedId = uploadId;
    const report = (sent: number) => onProgress?.(Math.min(sent / file.size, 1));
    const status = () => driveService.uploadStatus(workspaceSlug, projectId, issueId, openedId);

    let offset = 0;
    let throughServer = false;
    while (offset < file.size) {
      signal?.throwIfAborted();
      const size = throughServer ? session.relay_chunk_size : session.chunk_size;
      const chunk = file.slice(offset, Math.min(offset + size, file.size));
      const from = offset;
      if (!throughServer) {
        try {
          // oxlint-disable-next-line no-await-in-loop -- Google takes a file's pieces one after another, in order
          const answer = await putDirect(
            session.upload_url,
            chunk,
            from,
            file.size,
            (loaded) => report(from + loaded),
            signal
          );
          offset = answer.done ? file.size : answer.received;
          continue;
        } catch (failure) {
          if (failure instanceof DOMException) throw failure;
          throughServer = true;
          // Google may have kept part of the piece; carry on from what it has.
          // oxlint-disable-next-line no-await-in-loop -- once, when switching to the relay
          const answer: TDriveUploadAnswer = await status();
          if (answer.done) return answer.file;
          offset = answer.received;
          continue;
        }
      }
      // oxlint-disable-next-line no-await-in-loop -- the relay forwards each piece before taking the next
      const answer = await driveService.relayChunk(
        workspaceSlug,
        projectId,
        issueId,
        openedId,
        chunk,
        from,
        (loaded) => report(from + loaded),
        signal
      );
      if (answer.done) {
        report(file.size);
        return answer.file;
      }
      offset = answer.received;
    }

    // Every byte went straight to Google; the server confirms it with Google and records the file.
    const answer = await status();
    if (!answer.done) throw new DriveUploadError("Google Drive did not receive the whole file.", "DRIVE_INCOMPLETE");
    report(file.size);
    return answer.file;
  } catch (failure) {
    // A file that never arrived leaves no record behind. Best effort: the failure is what gets reported.
    if (uploadId) void driveService.removeFile(workspaceSlug, projectId, issueId, uploadId).catch(() => undefined);
    throw asUploadError(failure);
  }
}
