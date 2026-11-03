/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useSyncExternalStore } from "react";
import { v4 as uuidv4 } from "uuid";
// local imports
import type { TDriveUploadOptions } from "./upload";

export type TEditorUpload = { id: string; name: string; size: number; progress: number };

/**
 * Files on their way to Drive from an editor, per editor. The editor itself only
 * shows a placeholder where a file was dropped; this is where the progress and a
 * way to stop each one live, and what holds back sending a comment meanwhile.
 */
let uploads: Readonly<Record<string, readonly TEditorUpload[]>> = {};
const controllers = new Map<string, AbortController>();
const listeners = new Set<() => void>();
const NONE: readonly TEditorUpload[] = [];

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

const change = (key: string, rows: readonly TEditorUpload[]) => {
  const next = { ...uploads };
  if (rows.length) next[key] = rows;
  else delete next[key];
  uploads = next;
  listeners.forEach((listener) => listener());
};

/** The uploads of one editor, as they go. */
export const useEditorUploads = (key: string | undefined) =>
  useSyncExternalStore(subscribe, () => (key ? (uploads[key] ?? NONE) : NONE));

export const stopEditorUpload = (id: string) => controllers.get(id)?.abort();

/**
 * For an editor whose files go to Drive: the key of its list of uploads, whether
 * any are still going, and its submit, held back until they are done.
 */
export const useEditorUploadGate = <E>(
  editorId: string,
  sendsToDrive: boolean,
  submit: ((event: E) => void) | undefined
) => {
  const uploadsKey = sendsToDrive ? editorId : undefined;
  const isUploading = useEditorUploads(uploadsKey).length > 0;
  const gatedSubmit = (event: E) => {
    if (!isUploading) submit?.(event);
  };
  return { uploadsKey, isUploading, submit: gatedSubmit };
};

/**
 * Run one upload as part of an editor's list: it shows there with its progress
 * until it ends, however it ends, and stopping it there aborts it here.
 */
export async function trackEditorDriveUpload<T>(
  key: string,
  file: File,
  run: (options: Required<TDriveUploadOptions>) => Promise<T>
): Promise<T> {
  const id = uuidv4();
  const controller = new AbortController();
  controllers.set(id, controller);
  change(key, [...(uploads[key] ?? NONE), { id, name: file.name, size: file.size, progress: 0 }]);
  const onProgress = (fraction: number) => {
    const progress = Math.round(fraction * 100);
    const rows = uploads[key] ?? NONE;
    // Whole percents only: the browser reports far more often than anybody can read.
    if (rows.some((row) => row.id === id && row.progress !== progress))
      change(
        key,
        rows.map((row) => (row.id === id ? Object.assign({}, row, { progress }) : row))
      );
  };
  try {
    return await run({ onProgress, signal: controller.signal });
  } finally {
    controllers.delete(id);
    change(
      key,
      (uploads[key] ?? NONE).filter((row) => row.id !== id)
    );
  }
}
