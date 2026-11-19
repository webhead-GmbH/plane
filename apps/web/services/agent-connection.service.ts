/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

/** SWR key for the list of apps the signed-in person has connected. */
export const AGENT_CONNECTIONS_LIST = "AGENT_CONNECTIONS_LIST";

/** What a connected app is allowed to see or do, as the server words it (English; the web app translates by `id`). */
export type TAgentScope = {
  id: string;
  title: string;
  description: string;
  /** Whether the scope lets the app change anything. */
  writes: boolean;
};

/** The account on the app's side that is being linked. Typed by a stranger and passed on by the app: never trusted. */
export type TAgentLinkedAccount = {
  provider: string;
  id: string;
  username: string;
  name: string;
};

/** What the person is being asked to approve. */
export type TAgentConsent = {
  client: { name: string; description: string };
  account: TAgentLinkedAccount;
  scopes: TAgentScope[];
  /** The Plane account the app would be linked to. */
  user: { id: string; display_name: string; email: string };
  expires_at: string;
  /** Sent back with the decision to prove this page is the one that showed the request. */
  nonce: string;
};

export type TAgentConnection = {
  id: string;
  app: { name: string; description: string };
  account: TAgentLinkedAccount;
  scopes: TAgentScope[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
};

/** The error body every connected-app endpoint answers with. */
export type TAgentError = {
  error: string;
  error_description?: string;
};

export class AgentConnectionService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getConsent(requestToken: string): Promise<TAgentConsent> {
    return this.get(`/api/agent/connect/${encodeURIComponent(requestToken)}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Says yes. Resolves to the address to send the person on to, carrying the code. */
  async approve(requestToken: string, nonce: string): Promise<{ redirect_to: string }> {
    return this.post(`/api/agent/connect/${encodeURIComponent(requestToken)}/approve/`, { nonce })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Says no. Resolves to the address to send the person on to, carrying the refusal. */
  async deny(requestToken: string, nonce: string): Promise<{ redirect_to: string }> {
    return this.post(`/api/agent/connect/${encodeURIComponent(requestToken)}/deny/`, { nonce })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async listConnections(): Promise<TAgentConnection[]> {
    return this.get(`/api/agent/connections/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Takes an app's access back. It stops working on its very next call. */
  async revokeConnection(connectionId: string): Promise<void> {
    return this.delete(`/api/agent/connections/${connectionId}/`)
      .then(() => undefined)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
