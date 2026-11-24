/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { EmptyStateCompact } from "@plane/blocks/empty-state";
import { useTranslation } from "@plane/i18n";
// components
import { ConnectedAppsList } from "@/components/agent/connected-apps/list";
import { ProfileSettingsHeading } from "@/components/settings/profile/heading";
// services
import { AGENT_CONNECTIONS_LIST, AgentConnectionService } from "@/services/agent-connection.service";

const agentConnectionService = new AgentConnectionService();

/** The apps the person has allowed to act for them, with a way to take that back. */
export const ConnectedAppsProfileSettings = observer(function ConnectedAppsProfileSettings() {
  // translation
  const { t } = useTranslation();
  // fetching
  const {
    data: connections,
    error,
    mutate,
  } = useSWR(AGENT_CONNECTIONS_LIST, () => agentConnectionService.listConnections(), {
    // Back from another tab after approving or revoking somewhere else, the list should be true.
    revalidateOnFocus: true,
  });

  return (
    <div className="flex size-full flex-col gap-4">
      <ProfileSettingsHeading
        title={t("agent.connected_apps.title")}
        description={t("agent.connected_apps.description")}
      />
      {error && !connections ? (
        <EmptyStateCompact
          assetKey="unknown"
          assetClassName="size-20"
          title={t("agent.connected_apps.load_error.title")}
          description={t("agent.connected_apps.load_error.description")}
          customButton={
            <Button variant="secondary" size="md" stretch="auto" label={t("common.retry")} onClick={() => mutate()} />
          }
          align="center"
          rootClassName="rounded-lg border border-subtle bg-surface-1 py-10"
        />
      ) : !connections ? (
        <div className="h-32 w-full animate-pulse rounded-lg bg-layer-1" aria-hidden />
      ) : connections.length === 0 ? (
        <EmptyStateCompact
          assetKey="link"
          assetClassName="size-20"
          title={t("agent.connected_apps.empty.title")}
          description={t("agent.connected_apps.empty.description")}
          align="center"
          rootClassName="rounded-lg border border-subtle bg-surface-1 py-10"
        />
      ) : (
        <ConnectedAppsList connections={connections} />
      )}
    </div>
  );
});
