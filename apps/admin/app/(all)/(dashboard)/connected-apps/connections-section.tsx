/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { Skeleton } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { InstanceAgentAppService } from "@plane/services";
import type { TAgentApp, TAgentAppConnection } from "@plane/types";
// local
import { formatMoment, showError } from "./helpers";

const service = new InstanceAgentAppService();

type Props = {
  app: TAgentApp;
  /** The app after something ended connections, so its card shows the new count. */
  onChanged: (app: TAgentApp) => void;
};

/** `null` is nothing being asked; `"all"` is every connection; otherwise the connection being ended. */
type TEnding = null | "all" | TAgentAppConnection;

/** The people who have the app connected, and a way to end a connection that should not be there. */
export function ConnectionsSection(props: Props) {
  const { app, onChanged } = props;
  const { data, error, isLoading, mutate } = useSWR(`AGENT_APP_CONNECTIONS_${app.client_id}`, () =>
    service.connections(app.client_id)
  );
  const [ending, setEnding] = useState<TEnding>(null);
  const [isEnding, setIsEnding] = useState(false);

  const confirmEnd = async () => {
    if (ending === null) return;
    setIsEnding(true);
    try {
      const result = await service.endConnections(app.client_id, ending === "all" ? undefined : ending.id);
      onChanged(result.app);
      await mutate();
      setToast({
        type: "success",
        title: result.ended === 1 ? "Connection ended" : "Connections ended",
        message: "The app can no longer act for them. If events are on, the app is told the connection ended.",
      });
      setEnding(null);
    } catch (err) {
      showError("The connection was not ended", err);
    } finally {
      setIsEnding(false);
    }
  };

  const connections = data?.results ?? [];

  return (
    <section className="space-y-3" aria-labelledby={`connections-${app.client_id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 id={`connections-${app.client_id}`} className="text-body-sm-medium text-primary">
          Connections {data ? <span className="text-tertiary">• {data.total}</span> : null}
        </h4>
        {data && data.total > 0 && (
          <Button
            variant="ghost"
            size="sm"
            stretch="auto"
            onClick={() => setEnding("all")}
            label="End all connections"
          />
        )}
      </div>
      <p className="text-body-xs-regular text-tertiary">
        The people who have connected this app to their Plane account. Ending a connection stops the app at once; the
        person can connect it again.
      </p>
      {isLoading ? (
        <Skeleton className="space-y-2">
          <Skeleton.Item height="48px" width="100%" />
          <Skeleton.Item height="48px" width="100%" />
        </Skeleton>
      ) : error ? (
        <p role="alert" className="text-body-xs-regular text-danger-primary">
          The connections could not be loaded.
        </p>
      ) : connections.length === 0 ? (
        <p className="rounded-lg border border-dashed border-subtle px-3 py-4 text-center text-body-xs-regular text-tertiary">
          Nobody has connected this app yet.
        </p>
      ) : (
        <>
          <ul className="divide-y divide-subtle rounded-lg border border-subtle">
            {connections.map((connection) => {
              const account = [
                connection.account.provider,
                connection.account.username && `@${connection.account.username}`,
              ]
                .filter(Boolean)
                .join(" · ");
              return (
                <li key={connection.id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5">
                  <div className="min-w-0 space-y-0.5">
                    <div className="truncate text-body-sm-medium text-primary">
                      {connection.user.display_name}{" "}
                      <span className="text-body-xs-regular text-tertiary">{connection.user.email}</span>
                    </div>
                    <div className="text-body-xs-regular text-tertiary">
                      {account && <>{account} · </>}
                      connected {formatMoment(connection.created_at)} · last used{" "}
                      {formatMoment(connection.last_used_at)}
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" stretch="auto" onClick={() => setEnding(connection)} label="End" />
                </li>
              );
            })}
          </ul>
          {data && data.total > connections.length && (
            <p className="text-body-xs-regular text-tertiary">
              Showing the newest {connections.length} of {data.total}.
            </p>
          )}
        </>
      )}
      <ConfirmDialog
        isOpen={ending !== null}
        handleClose={() => setEnding(null)}
        handleSubmit={confirmEnd}
        isSubmitting={isEnding}
        variant="danger"
        title={ending === "all" ? "End every connection?" : "End this connection?"}
        content={
          ending === "all"
            ? `Everyone who connected ${app.name} will have it cut off at once. They can connect it again.`
            : `${app.name} will no longer be able to act for ${ending === null ? "this person" : ending.user.display_name}. They can connect it again.`
        }
        primaryButtonText={{ default: "End", loading: "Ending" }}
        secondaryButtonText="Keep"
      />
    </section>
  );
}
