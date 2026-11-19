/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { useTranslation } from "@plane/i18n";
import { renderFormattedDate } from "@plane/utils";
// services
import type { TAgentConnection } from "@/services/agent-connection.service";
// local imports
import { handleLabel, providerLabel } from "../helpers";
import { useScopeText } from "../use-scope-text";
import { RevokeConnectionDialog } from "./revoke-dialog";

/** The Revoke button of one connection, with the confirmation it opens. */
function RevokeAction(props: { connection: TAgentConnection }) {
  const { connection } = props;
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <RevokeConnectionDialog connection={connection} isOpen={isOpen} onClose={() => setIsOpen(false)} />
      <Button
        variant="danger-outline"
        size="sm"
        stretch="auto"
        label={t("agent.connected_apps.revoke")}
        // The label alone does not say which app it is for once a list has more than one.
        aria-label={t("agent.connected_apps.revoke_aria", { app: connection.app.name })}
        onClick={() => setIsOpen(true)}
      />
    </>
  );
}

/** What the app has been allowed to do, one pill each, with the longer wording on hover. */
function AccessPills(props: { connection: TAgentConnection }) {
  const { connection } = props;
  const { t } = useTranslation();
  const scopeText = useScopeText();

  return (
    <ul className="flex flex-wrap gap-1" aria-label={t("agent.connected_apps.fields.access")}>
      {connection.scopes.map((scope) => {
        const text = scopeText(scope);
        return (
          <li key={scope.id}>
            <Tooltip label={text.description || text.title}>
              <span>
                <Badge variant={scope.writes ? "warning" : "neutral"} size="xs" label={text.title} />
              </span>
            </Tooltip>
          </li>
        );
      })}
    </ul>
  );
}

function DateField(props: { label: string; value: string | null | undefined; empty: string }) {
  const { label, value, empty } = props;
  const formatted = value ? renderFormattedDate(value) : undefined;
  return (
    <div className="flex gap-1">
      <dt className="text-tertiary">{label}</dt>
      <dd className={formatted ? "text-secondary" : "text-tertiary"}>{formatted ?? empty}</dd>
    </div>
  );
}

function ConnectionRow(props: { connection: TAgentConnection }) {
  const { connection } = props;
  const { t } = useTranslation();
  const { account } = connection;
  // Typed by somebody else and passed on by the app, so isolated from what is around it.
  const who = [providerLabel(account.provider), handleLabel(account.username) || account.name || account.id]
    .filter(Boolean)
    .join(" · ");

  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate text-body-sm-medium text-primary">{connection.app.name}</span>
          <span className="truncate text-body-xs-regular text-tertiary">
            <bdi dir="auto">{who}</bdi>
          </span>
        </div>
        <AccessPills connection={connection} />
        <dl className="flex flex-wrap gap-x-4 gap-y-1 text-caption-sm-regular">
          <DateField label={t("agent.connected_apps.fields.linked")} value={connection.created_at} empty="" />
          <DateField
            label={t("agent.connected_apps.fields.last_used")}
            value={connection.last_used_at}
            empty={t("agent.connected_apps.not_used_yet")}
          />
          <DateField
            label={t("agent.connected_apps.fields.expires")}
            value={connection.expires_at}
            empty={t("agent.connected_apps.no_expiry")}
          />
        </dl>
      </div>
      <div className="shrink-0">
        <RevokeAction connection={connection} />
      </div>
    </li>
  );
}

/** The apps a person has connected: which app, as whom, with what access, since when, and a way to end it. */
export function ConnectedAppsList(props: { connections: TAgentConnection[] }) {
  return (
    <ul className="flex w-full flex-col divide-y divide-subtle rounded-lg border border-subtle bg-surface-1">
      {props.connections.map((connection) => (
        <ConnectionRow key={connection.id} connection={connection} />
      ))}
    </ul>
  );
}
