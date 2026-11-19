/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { mutate } from "swr";
// plane imports
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
// services
import { AGENT_CONNECTIONS_LIST, AgentConnectionService } from "@/services/agent-connection.service";
import type { TAgentConnection } from "@/services/agent-connection.service";

const agentConnectionService = new AgentConnectionService();

type Props = {
  connection: TAgentConnection;
  isOpen: boolean;
  onClose: () => void;
};

/** Asks before taking an app's access back: from the next call it makes, it works no more. */
export function RevokeConnectionDialog(props: Props) {
  const { connection, isOpen, onClose } = props;
  // states
  const [isRevoking, setIsRevoking] = useState(false);
  // translation
  const { t } = useTranslation();

  const handleRevoke = async () => {
    setIsRevoking(true);
    try {
      await agentConnectionService.revokeConnection(connection.id);
      setToast({
        type: "success",
        title: t("agent.connected_apps.revoke_success.title"),
        message: t("agent.connected_apps.revoke_success.message", { app: connection.app.name }),
      });
      // Gone from the list at once; the refetch behind it confirms it.
      await mutate<TAgentConnection[]>(
        AGENT_CONNECTIONS_LIST,
        (previous) => (previous ?? []).filter((item) => item.id !== connection.id),
        { revalidate: true }
      );
      onClose();
    } catch {
      setToast({
        type: "error",
        title: t("agent.connected_apps.revoke_error.title"),
        message: t("agent.connected_apps.revoke_error.message"),
      });
    } finally {
      setIsRevoking(false);
    }
  };

  return (
    <ConfirmDialog
      isOpen={isOpen}
      handleClose={onClose}
      handleSubmit={handleRevoke}
      isSubmitting={isRevoking}
      variant="danger"
      title={t("agent.connected_apps.revoke_title", { app: connection.app.name })}
      content={t("agent.connected_apps.revoke_description", { app: connection.app.name })}
      primaryButtonText={{
        loading: t("agent.connected_apps.revoking"),
        default: t("agent.connected_apps.revoke_confirm"),
      }}
      secondaryButtonText={t("common.cancel")}
    />
  );
}
