/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { API_BASE_URL } from "@plane/constants";
import type {
  TAgentApp,
  TAgentAppConnections,
  TAgentAppEventTest,
  TAgentAppList,
  TAgentAppPayload,
  TAgentAppWithSecret,
} from "@plane/types";
// api service
import { APIService } from "../api.service";

/**
 * The instance administrators' calls for the apps people may connect to their Plane account.
 * They use the admin app's own session, so they only work from the admin app.
 * @extends {APIService}
 */
export class InstanceAgentAppService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private path(clientId: string, ...tail: string[]) {
    return `/api/instances/agent-apps/${encodeURIComponent(clientId)}/${tail.map((part) => `${part}/`).join("")}`;
  }

  async list(): Promise<TAgentAppList> {
    return this.get("/api/instances/agent-apps/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Registers an app. The secret in the answer is shown once and cannot be read again. */
  async create(data: TAgentAppPayload): Promise<TAgentAppWithSecret> {
    return this.post("/api/instances/agent-apps/", data)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async update(clientId: string, data: TAgentAppPayload): Promise<TAgentApp> {
    return this.patch(this.path(clientId), data)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Makes a new secret; the old one stops working at once. */
  async replaceSecret(clientId: string): Promise<TAgentAppWithSecret> {
    return this.post(this.path(clientId, "secret"))
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async setEventsAddress(clientId: string, url: string): Promise<TAgentApp> {
    return this.put(this.path(clientId, "webhook"), { url })
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async turnEventsOff(clientId: string): Promise<TAgentApp> {
    return this.delete(this.path(clientId, "webhook"))
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Shows the secret deliveries are signed with, or, with `replace`, makes a new one. */
  async eventsSecret(clientId: string, replace = false): Promise<{ app: TAgentApp; webhook_secret: string }> {
    return this.post(this.path(clientId, "webhook", "secret"), { replace })
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async testEvents(clientId: string): Promise<TAgentAppEventTest> {
    return this.post(this.path(clientId, "webhook", "test"))
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async connections(clientId: string): Promise<TAgentAppConnections> {
    return this.get(this.path(clientId, "connections"))
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Ends one connection, or every connection the app has. */
  async endConnections(clientId: string, connectionId?: string): Promise<{ ended: number; app: TAgentApp }> {
    return this.delete(
      connectionId ? this.path(clientId, "connections", connectionId) : this.path(clientId, "connections")
    )
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
