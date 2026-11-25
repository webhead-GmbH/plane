/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// The apps people may connect to their Plane account (a chat bot, say), as the instance
// administrators' "Connected apps" screen sees them. Mirrors `plane/agent/views/admin.py`.

export type TAgentScope = {
  id: string;
  title: string;
  description: string;
  /** Lets the app change things, as the person who connected it. */
  writes: boolean;
  /** Lets the app see other people's information, people who never approved anything themselves. */
  others: boolean;
};

export type TAgentAppEvents = {
  url: string;
  /** `given_up`: Plane stopped sending after too many failures in a row. */
  state: "off" | "on" | "given_up";
  failures: number;
  disabled_at: string | null;
};

export type TAgentApp = {
  client_id: string;
  name: string;
  description: string;
  redirect_uris: string[];
  allowed_scopes: string[];
  is_active: boolean;
  /** People who have it connected right now. */
  connections: number;
  webhook: TAgentAppEvents;
  secret_rotated_at: string | null;
  created_at: string;
};

export type TAgentAppList = {
  apps: TAgentApp[];
  scopes: TAgentScope[];
  default_scopes: string[];
};

export type TAgentAppPayload = {
  name?: string;
  description?: string;
  redirect_uris?: string[];
  allowed_scopes?: string[];
  is_active?: boolean;
};

/** Only the answer to registering an app, or replacing its secret, carries the secret. */
export type TAgentAppWithSecret = {
  app: TAgentApp;
  client_secret: string;
};

export type TAgentAppConnection = {
  id: string;
  user: { id: string; display_name: string; email: string };
  scopes: string[];
  account: { provider: string; username: string; name: string };
  created_at: string;
  last_used_at: string | null;
};

export type TAgentAppConnections = {
  total: number;
  results: TAgentAppConnection[];
};

export type TAgentAppEventTest = {
  heard: boolean;
  detail: string;
};
