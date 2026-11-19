/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

/** Where each Plane project's CRM id comes from. */
export type TCrmProjectMappingSource = "custom_field" | "identifier";

export type TCrmIntegration = {
  id?: string;
  workspace?: string;
  crm_api_url?: string;
  project_mapping_source?: TCrmProjectMappingSource;
  crm_project_id_custom_field?: string | null;
  is_active?: boolean;
  last_synced_at?: string | null;
  has_api_key?: boolean;
  created_at?: string;
  updated_at?: string;
};

/** Payload sent when creating/updating; `crm_api_key` is write-only. */
export type TCrmIntegrationPayload = Partial<TCrmIntegration> & {
  crm_api_key?: string;
};

/** What changing a project's Project ID would do outside Plane, so a screen can ask before saving it. */
export type TIdentifierChangeImpact = {
  /** Set only when the CRM maps projects by identifier. */
  crm: {
    /** The CRM project number the project is filed under now; null when its Project ID is not a number. */
    current: number | null;
    /** The one it would be filed under; null when the new Project ID is not a number. */
    target: number | null;
    /** How many CRM tasks would move to it, with their timers and hours. */
    tasks: number;
    /** What the CRM calls that project, when it could be read. */
    target_name: string | null;
  } | null;
  /** Set only when the project has a Google Drive folder. */
  drive: {
    folder: { from: string; to: string } | null;
    work_items: number;
  } | null;
};

export type TCrmConnectionTest = {
  success: boolean;
  projects_count?: number;
  error?: string;
};

export class CrmIntegrationService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async identifierChangeImpact(
    workspaceSlug: string,
    projectId: string,
    identifier: string
  ): Promise<TIdentifierChangeImpact> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/identifier-change/`, {
      params: { identifier },
    })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async retrieve(workspaceSlug: string): Promise<TCrmIntegration> {
    return this.get(`/api/workspaces/${workspaceSlug}/crm-integration/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async create(workspaceSlug: string, data: TCrmIntegrationPayload): Promise<TCrmIntegration> {
    return this.post(`/api/workspaces/${workspaceSlug}/crm-integration/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async update(workspaceSlug: string, data: TCrmIntegrationPayload): Promise<TCrmIntegration> {
    return this.patch(`/api/workspaces/${workspaceSlug}/crm-integration/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async destroy(workspaceSlug: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/crm-integration/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async testConnection(
    workspaceSlug: string,
    data: { crm_api_url?: string; crm_api_key?: string }
  ): Promise<TCrmConnectionTest> {
    return this.post(`/api/workspaces/${workspaceSlug}/crm-integration/test/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Push every existing work item and worklog to the CRM once.
   * Day-to-day syncing is event-driven, so this is only needed to seed a newly connected CRM.
   */
  async backfill(workspaceSlug: string): Promise<{ success: boolean; message: string }> {
    return this.post(`/api/workspaces/${workspaceSlug}/crm-integration/sync/`, {})
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** List active project custom fields, used to populate the project-id field selector. */
  async fetchProjectCustomFields(workspaceSlug: string): Promise<{ id: string; display_name: string }[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/custom-fields/active/`, {
      params: { entity_type: "project" },
    })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
