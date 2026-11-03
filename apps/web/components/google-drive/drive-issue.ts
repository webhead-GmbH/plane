/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo } from "react";
import { observable, runInAction } from "mobx";
import useSWR, { mutate } from "swr";
// plane imports
import { setToast } from "@plane/blocks/toast";
// services
import { GoogleDriveService } from "@/services/google-drive.service";
// local imports
import { I18N, driveErrorMessage } from "./errors";
import { isUploadStopped, uploadFileToDrive } from "./upload";
import type { TDriveUploadTarget } from "./upload";

const driveService = new GoogleDriveService();

type TTranslate = (key: string, values?: Record<string, unknown>) => string;

export type TDriveUploadRow = { id: string; name: string; size: number; type: string; progress: number };

/**
 * Files on their way to Drive, per work item. Shared, because the Attach button
 * starts uploads that the attachments list shows — two components that do not
 * share a parent close enough to hold the state.
 */
export const driveUploads = observable.map<string, TDriveUploadRow[]>();
// Kept apart from the rows, which MobX makes observable: a controller is a handle, not state.
const uploadControllers = new Map<string, AbortController>();

/** Stop an attachment on its way to Drive; it leaves nothing behind. */
export const stopDriveUpload = (id: string) => uploadControllers.get(id)?.abort();

const issueKey = (workspaceSlug: string, projectId: string, issueId: string) =>
  ["GDRIVE_ISSUE", workspaceSlug, projectId, issueId] as const;

/**
 * Whether this work item's files go to Drive, and the ones attached to it. Asked
 * again on returning to the tab, since a project may have been linked meanwhile,
 * and every two seconds while its older attachments are moving there.
 */
export const useDriveIssue = (workspaceSlug?: string, projectId?: string, issueId?: string) =>
  useSWR(
    workspaceSlug && projectId && issueId ? issueKey(workspaceSlug, projectId, issueId) : null,
    () => driveService.issueFiles(workspaceSlug as string, projectId as string, issueId as string),
    { shouldRetryOnError: false, refreshInterval: (data) => (data?.moving ? 2000 : 0) }
  );

/** Forget what every work item said about Drive: a project's folder changed. */
export const forgetDriveIssues = () =>
  mutate((key) => Array.isArray(key) && key[0] === "GDRIVE_ISSUE", undefined, { revalidate: true });

/**
 * Where a work item's editor sends images and files: its Drive folder, or nowhere special.
 *
 * An editor takes its file handling once, when it is made, so `isDriveLoading`
 * says to hold off making it until the answer is in; it usually already is,
 * since the attachments section asks the same question.
 */
export const useDriveTarget = (
  workspaceSlug: string | undefined,
  projectId: string | undefined,
  issueId: string | undefined,
  source: TDriveUploadTarget["source"]
): { driveTarget: TDriveUploadTarget | undefined; isDriveLoading: boolean } => {
  const { data, error } = useDriveIssue(workspaceSlug, projectId, issueId);
  const enabled = Boolean(data?.enabled);
  const driveTarget = useMemo(
    () =>
      enabled && workspaceSlug && projectId && issueId ? { workspaceSlug, projectId, issueId, source } : undefined,
    [enabled, workspaceSlug, projectId, issueId, source]
  );
  const asked = Boolean(workspaceSlug && projectId && issueId);
  return { driveTarget, isDriveLoading: asked && data === undefined && error === undefined };
};

/** How many of a work item's files are in Google Drive or on their way there. */
export const useDriveFileCount = (workspaceSlug?: string, projectId?: string, issueId?: string) => {
  const { data } = useDriveIssue(workspaceSlug, projectId, issueId);
  return (data?.files.length ?? 0) + (issueId ? (driveUploads.get(issueId)?.length ?? 0) : 0);
};

export const refreshDriveIssue = (workspaceSlug: string, projectId: string, issueId: string) =>
  mutate(issueKey(workspaceSlug, projectId, issueId));

const setRow = (issueId: string, id: string, change: Partial<TDriveUploadRow> | null) =>
  runInAction(() => {
    const rows = driveUploads.get(issueId) ?? [];
    const next =
      change === null
        ? rows.filter((row) => row.id !== id)
        : rows.map((row) => (row.id === id ? Object.assign({}, row, change) : row));
    if (next.length) driveUploads.set(issueId, next);
    else driveUploads.delete(issueId);
  });

/**
 * Upload attachments to the work item's Drive folder, several at once, with no
 * limit on size, type or number. Each failure is said out loud with its reason.
 */
export const attachFilesToDrive = async (files: File[], target: Omit<TDriveUploadTarget, "source">, t: TTranslate) => {
  const { workspaceSlug, projectId, issueId } = target;
  await Promise.all(
    files.map(async (file) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const controller = new AbortController();
      uploadControllers.set(id, controller);
      runInAction(() =>
        driveUploads.set(issueId, [
          ...(driveUploads.get(issueId) ?? []),
          { id, name: file.name, size: file.size, type: file.type, progress: 0 },
        ])
      );
      try {
        await uploadFileToDrive(
          file,
          { ...target, source: "attachment" },
          {
            signal: controller.signal,
            onProgress: (fraction) => setRow(issueId, id, { progress: Math.round(fraction * 100) }),
          }
        );
        await refreshDriveIssue(workspaceSlug, projectId, issueId);
      } catch (failure) {
        // Stopped by the person who started it: nothing to say.
        if (isUploadStopped(failure)) return;
        setToast({
          type: "error",
          title: t(`${I18N}.attachments.upload_failed`, { name: file.name }),
          message: driveErrorMessage(failure, t),
        });
      } finally {
        uploadControllers.delete(id);
        setRow(issueId, id, null);
      }
    })
  );
};
