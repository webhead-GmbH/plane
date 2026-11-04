/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TDriveFolderRef = { id: string; name: string; path?: string; url?: string };

export type TDriveConnection = {
  client_id: string;
  has_client_secret: boolean;
  /** What to register as the authorised redirect URI on the Google client. */
  redirect_uri: string;
  connected: boolean;
  account_email: string;
  connected_at: string | null;
  root_folder: TDriveFolderRef | null;
  auto_link_new_projects: boolean;
};

export type TDriveConnectionPayload = {
  client_id?: string;
  client_secret?: string;
  /** A folder id, a pasted Drive folder link, "root" for My Drive, or "" to clear. */
  root_folder?: string;
  auto_link_new_projects?: boolean;
};

export type TDriveBrowseItem = {
  id: string;
  name: string;
  kind: "my_drive" | "shared_with_me" | "shared_drive" | "folder";
};

export type TDriveFolderSuggestion = {
  id: string;
  name: string;
  score: number;
  /** The one folder that is clearly this project's: what linking the clear matches would pick. */
  clear: boolean;
};

export type TDriveProjectRow = {
  /** new_folder_name: what "Create folder" calls it, the team's "209 - Name". */
  project: { id: string; name: string; identifier: string; new_folder_name: string };
  folder: (TDriveFolderRef & { method: "chosen" | "matched" | "created" }) | null;
  suggestions: TDriveFolderSuggestion[];
};

export type TDriveProjects = { folders: { id: string; name: string }[]; projects: TDriveProjectRow[] };

export type TDriveFileSource = "attachment" | "description" | "comment";

export type TDriveFile = {
  id: string;
  issue_id: string;
  name: string;
  mime_type: string;
  size: number;
  source: TDriveFileSource;
  state: "uploading" | "uploaded";
  is_image: boolean;
  web_view_link: string;
  /** API path of a resized image, for images only. */
  preview_path: string;
  created_by: string | null;
  created_at: string;
  uploaded_at: string | null;
};

export type TDriveIssue = {
  enabled: boolean;
  folder_url: string;
  files: TDriveFile[];
  /** Its attachments from before the folder are being moved there. */
  moving: boolean;
};

/** Attachments in linked projects still on the Plane server. */
export type TDrivePlaneFiles = { count: number; size: number; moving: boolean };

export type TDriveUploadStart = {
  file: TDriveFile;
  /** Google's upload session: the browser sends the bytes here directly where it can. */
  upload_url: string;
  chunk_size: number;
  /** The largest piece the Plane server takes, for when Google refuses the browser. */
  relay_chunk_size: number;
};

export type TDriveUploadAnswer = { done: true; file: TDriveFile } | { done: false; received: number };

/** What the server says when a Drive call fails: a sentence and a code to choose wording by. */
export type TDriveError = { error?: string; code?: string };

const fail = (error: unknown): never => {
  throw (error as { response?: { data?: TDriveError } })?.response?.data ?? { code: "DRIVE_ERROR" };
};

export class GoogleDriveService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private workspace(slug: string) {
    return `/api/workspaces/${slug}/drive`;
  }

  private issue(slug: string, projectId: string, issueId: string) {
    return `/api/workspaces/${slug}/projects/${projectId}/issues/${issueId}/drive`;
  }

  // ─── The workspace's connection ──────────────────────────────────────────

  async connection(slug: string): Promise<TDriveConnection> {
    return this.get(`${this.workspace(slug)}/connection/`)
      .then((response) => response?.data)
      .catch(fail);
  }

  async updateConnection(slug: string, data: TDriveConnectionPayload): Promise<TDriveConnection> {
    return this.patch(`${this.workspace(slug)}/connection/`, data)
      .then((response) => response?.data)
      .catch(fail);
  }

  async disconnect(slug: string): Promise<TDriveConnection> {
    return this.delete(`${this.workspace(slug)}/connection/`)
      .then((response) => response?.data)
      .catch(fail);
  }

  /** Where to send the admin to sign in with Google. */
  async authorizationUrl(slug: string): Promise<string> {
    return this.post(`${this.workspace(slug)}/connection/authorize/`)
      .then((response) => response?.data?.url)
      .catch(fail);
  }

  async folders(slug: string, parent = ""): Promise<TDriveBrowseItem[]> {
    return this.get(`${this.workspace(slug)}/folders/`, { params: parent ? { parent } : {} })
      .then((response) => response?.data?.items ?? [])
      .catch(fail);
  }

  // ─── Project folders ─────────────────────────────────────────────────────

  async projects(slug: string): Promise<TDriveProjects> {
    return this.get(`${this.workspace(slug)}/projects/`)
      .then((response) => response?.data)
      .catch(fail);
  }

  async linkSuggested(slug: string): Promise<{ linked: number }> {
    return this.post(`${this.workspace(slug)}/projects/link-suggested/`)
      .then((response) => response?.data)
      .catch(fail);
  }

  async setProjectFolder(
    slug: string,
    projectId: string,
    data: { folder_id: string } | { create: true }
  ): Promise<TDriveProjectRow> {
    return this.put(`${this.workspace(slug)}/projects/${projectId}/folder/`, data)
      .then((response) => response?.data)
      .catch(fail);
  }

  async unlinkProject(slug: string, projectId: string): Promise<void> {
    return this.delete(`${this.workspace(slug)}/projects/${projectId}/folder/`)
      .then(() => undefined)
      .catch(fail);
  }

  async planeFiles(slug: string): Promise<TDrivePlaneFiles> {
    return this.get(`${this.workspace(slug)}/plane-files/`)
      .then((response) => response?.data)
      .catch(fail);
  }

  /** Move every attachment in a linked project from the Plane server to Drive, in the background. */
  async moveAllPlaneFiles(slug: string): Promise<void> {
    return this.post(`${this.workspace(slug)}/plane-files/`)
      .then(() => undefined)
      .catch(fail);
  }

  // ─── A work item's files ─────────────────────────────────────────────────

  async issueFiles(slug: string, projectId: string, issueId: string): Promise<TDriveIssue> {
    return this.get(`${this.issue(slug, projectId, issueId)}/`)
      .then((response) => response?.data)
      .catch(fail);
  }

  /** Move the work item's attachments from the Plane server into its Drive folder, in the background. */
  async movePlaneFiles(slug: string, projectId: string, issueId: string): Promise<void> {
    return this.post(`${this.issue(slug, projectId, issueId)}/move-plane-files/`)
      .then(() => undefined)
      .catch(fail);
  }

  async startUpload(
    slug: string,
    projectId: string,
    issueId: string,
    data: { name: string; size: number; mime_type: string; source: TDriveFileSource }
  ): Promise<TDriveUploadStart> {
    return this.post(`${this.issue(slug, projectId, issueId)}/uploads/`, data)
      .then((response) => response?.data)
      .catch(fail);
  }

  /** How far an upload got; finishes it on the server once Google has every byte. */
  async uploadStatus(slug: string, projectId: string, issueId: string, uploadId: string): Promise<TDriveUploadAnswer> {
    return this.get(`${this.issue(slug, projectId, issueId)}/uploads/${uploadId}/`)
      .then((response) => response?.data)
      .catch(fail);
  }

  /** One piece of a file through the Plane server, for a browser Google will not take it from. */
  async relayChunk(
    slug: string,
    projectId: string,
    issueId: string,
    uploadId: string,
    chunk: Blob,
    start: number,
    onProgress?: (loaded: number) => void,
    signal?: AbortSignal
  ): Promise<TDriveUploadAnswer> {
    return this.put(`${this.issue(slug, projectId, issueId)}/uploads/${uploadId}/`, chunk, {
      // The offset goes in the address, not a Content-Range header, which CORS would refuse.
      params: { offset: start },
      headers: { "Content-Type": "application/octet-stream" },
      onUploadProgress: (event: { loaded: number }) => onProgress?.(event.loaded),
      signal,
    })
      .then((response) => response?.data)
      .catch(fail);
  }

  async removeFile(slug: string, projectId: string, issueId: string, fileId: string): Promise<void> {
    return this.delete(`${this.issue(slug, projectId, issueId)}/files/${fileId}/`)
      .then(() => undefined)
      .catch(fail);
  }

  /** Where an <img> can load a Drive image from, at about this many pixels on its long side. */
  previewUrl(slug: string, fileId: string, size = 800): string {
    return `${API_BASE_URL}${this.workspace(slug)}/files/${fileId}/preview/?size=${size}`;
  }
}
