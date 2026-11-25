/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { InstanceAgentAppService } from "@plane/services";
import type { TAgentApp, TAgentScope } from "@plane/types";
// components
import { CopyField } from "@/components/common/copy-field";
// local
import { ConnectionsSection } from "./connections-section";
import { EventsSection } from "./events-section";
import type { TRevealed } from "./helpers";
import { formatMoment, showError } from "./helpers";

const service = new InstanceAgentAppService();

type TSectionProps = {
  app: TAgentApp;
  /** Something about the app changed; use the new version. */
  onChanged: (app: TAgentApp) => void;
};

const EVENT_BADGE = {
  on: { variant: "success", label: "Events on" },
  off: { variant: "neutral", label: "Events off" },
  given_up: { variant: "danger", label: "Events stopped" },
} as const;

/** The client ID, which is not a secret, and the client secret, which is shown once and can only be replaced. */
function CredentialsSection(props: TSectionProps & { onReveal: (revealed: TRevealed) => void }) {
  const { app, onChanged, onReveal } = props;
  const [isAsking, setIsAsking] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const headingId = `agent-app-${app.client_id}-credentials`;

  const replaceSecret = async () => {
    setIsWorking(true);
    try {
      const result = await service.replaceSecret(app.client_id);
      onChanged(result.app);
      setIsAsking(false);
      onReveal({
        title: "New client secret",
        intro: `Give ${app.name} this secret in its own settings. The old one has stopped working.`,
        once: true,
        fields: [
          {
            label: "Client secret",
            value: result.client_secret,
            description: "How the app proves to Plane that it is the app.",
          },
        ],
      });
    } catch (error) {
      showError("The secret was not replaced", error);
    } finally {
      setIsWorking(false);
    }
  };

  return (
    <section className="space-y-3" aria-labelledby={headingId}>
      <h4 id={headingId} className="text-body-sm-medium text-primary">
        Credentials
      </h4>
      <CopyField
        label="Client ID"
        url={app.client_id}
        description="Not a secret. The app sends it with every request."
      />
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-subtle bg-layer-2 px-3 py-2.5">
        <div className="min-w-0 space-y-0.5">
          <div className="text-body-sm-medium text-primary">Client secret</div>
          <div className="text-body-xs-regular text-tertiary">
            Shown once, when it was made, and not kept anywhere.{" "}
            {app.secret_rotated_at ? `Replaced ${formatMoment(app.secret_rotated_at)}.` : ""}
          </div>
        </div>
        <Button variant="secondary" size="md" stretch="auto" onClick={() => setIsAsking(true)} label="Replace secret" />
      </div>
      <ConfirmDialog
        isOpen={isAsking}
        handleClose={() => setIsAsking(false)}
        handleSubmit={replaceSecret}
        isSubmitting={isWorking}
        variant="warning"
        title="Replace the client secret?"
        content={`The old secret stops working at once, so ${app.name} cannot ask Plane for anything until it has the new one. You will see the new secret once.`}
        primaryButtonText={{ default: "Replace secret", loading: "Replacing" }}
        secondaryButtonText="Keep the current one"
      />
    </section>
  );
}

/** Where people are sent back after they approve, and the most the app may ask them for. */
function AccessSection(props: { app: TAgentApp; scopes: TAgentScope[]; onEdit: () => void }) {
  const { app, scopes, onEdit } = props;
  const headingId = `agent-app-${app.client_id}-access`;
  const scopeById = new Map(scopes.map((scope) => [scope.id, scope]));
  const allowed = app.allowed_scopes.map((id) => scopeById.get(id)).filter((scope): scope is TAgentScope => !!scope);

  return (
    <section className="space-y-3" aria-labelledby={headingId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 id={headingId} className="text-body-sm-medium text-primary">
          Where people are sent back, and what it may ask for
        </h4>
        <Button variant="secondary" size="sm" stretch="auto" onClick={onEdit} label="Edit" />
      </div>
      <ul className="space-y-1">
        {app.redirect_uris.map((uri) => (
          <li key={uri}>
            <code className="text-body-xs-regular break-all text-secondary">{uri}</code>
          </li>
        ))}
      </ul>
      <ul className="flex flex-wrap gap-1.5">
        {allowed.map((scope) => {
          const notes = [scope.writes && "can make changes", scope.others && "sees other people's information"]
            .filter(Boolean)
            .join(", ");
          return (
            <li key={scope.id}>
              <Badge
                variant={notes ? "warning" : "neutral"}
                size="sm"
                label={scope.id}
                aria-label={notes ? `${scope.title}, ${notes}` : scope.title}
              />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** The emergency stop: an app that is off cannot be connected and its tokens stop working, nobody is disconnected. */
function SwitchSection(props: TSectionProps) {
  const { app, onChanged } = props;
  const [isAsking, setIsAsking] = useState(false);
  const [isWorking, setIsWorking] = useState(false);

  const switchApp = async () => {
    setIsWorking(true);
    try {
      const updated = await service.update(app.client_id, { is_active: !app.is_active });
      onChanged(updated);
      setIsAsking(false);
      setToast({
        type: "success",
        title: updated.is_active ? `${app.name} is on` : `${app.name} is off`,
        message: updated.is_active
          ? "People's connections work again."
          : "Its tokens stop working on their next call. Nobody is disconnected.",
      });
    } catch (error) {
      showError("The app was not changed", error);
    } finally {
      setIsWorking(false);
    }
  };

  return (
    <section className="flex flex-wrap items-center justify-between gap-3 border-t border-subtle pt-4">
      <div className="min-w-0 space-y-0.5">
        <div className="text-body-sm-medium text-primary">
          {app.is_active ? "Switch this app off" : "Switch this app back on"}
        </div>
        <div className="text-body-xs-regular text-tertiary">
          {app.is_active
            ? "Its tokens stop working and nobody can connect it. Connections are kept, so switching it back on restores them."
            : "Its tokens work again and people can connect it."}
        </div>
      </div>
      <Button
        variant={app.is_active ? "danger-outline" : "primary"}
        size="md"
        stretch="auto"
        onClick={() => setIsAsking(true)}
        label={app.is_active ? "Switch off" : "Switch on"}
      />
      <ConfirmDialog
        isOpen={isAsking}
        handleClose={() => setIsAsking(false)}
        handleSubmit={switchApp}
        isSubmitting={isWorking}
        variant={app.is_active ? "danger" : "primary"}
        title={app.is_active ? `Switch off ${app.name}?` : `Switch on ${app.name}?`}
        content={
          app.is_active
            ? "It stops working on its next call and nobody can connect it, until you switch it back on."
            : "It works again, with the connections people already have."
        }
        primaryButtonText={{ default: app.is_active ? "Switch off" : "Switch on", loading: "Saving" }}
        secondaryButtonText="Cancel"
      />
    </section>
  );
}

type TAppCardProps = TSectionProps & {
  scopes: TAgentScope[];
  isOpen: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onReveal: (revealed: TRevealed) => void;
};

/** One registered app: what it is at a glance, and, opened, everything an administrator does with it. */
export function AppCard(props: TAppCardProps) {
  const { app, scopes, isOpen, onToggle, onEdit, onChanged, onReveal } = props;
  const events = EVENT_BADGE[app.webhook.state];
  const panelId = `agent-app-${app.client_id}`;

  return (
    <article className="rounded-lg border border-subtle bg-layer-1">
      <div className="flex flex-wrap items-start justify-between gap-3 p-4">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-body-md-medium text-primary">{app.name}</h3>
            <Badge
              variant={app.is_active ? "success" : "neutral"}
              size="sm"
              label={app.is_active ? "On" : "Switched off"}
            />
            <Badge variant={events.variant} size="sm" label={events.label} />
          </div>
          {app.description && <p className="text-body-xs-regular text-secondary">{app.description}</p>}
          <p className="text-body-xs-regular text-tertiary">
            {app.connections === 1 ? "1 person" : `${app.connections} people`} connected · added{" "}
            {formatMoment(app.created_at)}
          </p>
        </div>
        <Button
          variant="secondary"
          size="md"
          stretch="auto"
          onClick={onToggle}
          aria-expanded={isOpen}
          aria-controls={panelId}
          label={isOpen ? "Hide details" : "Manage"}
        />
      </div>
      {isOpen && (
        <div id={panelId} className="space-y-6 border-t border-subtle p-4">
          <CredentialsSection app={app} onChanged={onChanged} onReveal={onReveal} />
          <AccessSection app={app} scopes={scopes} onEdit={onEdit} />
          <EventsSection key={app.client_id} app={app} onChanged={onChanged} onReveal={onReveal} />
          <ConnectionsSection app={app} onChanged={onChanged} />
          <SwitchSection app={app} onChanged={onChanged} />
        </div>
      )}
    </article>
  );
}
