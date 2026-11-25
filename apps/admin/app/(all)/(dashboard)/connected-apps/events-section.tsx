/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { InstanceAgentAppService } from "@plane/services";
import type { TAgentApp } from "@plane/types";
// local
import type { TRevealed } from "./helpers";
import { formatMoment, showError } from "./helpers";

const service = new InstanceAgentAppService();

type Props = {
  app: TAgentApp;
  onChanged: (app: TAgentApp) => void;
  onReveal: (revealed: TRevealed) => void;
};

type TBusy = "save" | "off" | "test" | "show" | "replace";
type TConfirm = "off" | "replace" | null;

const STATE_BADGE = {
  on: { variant: "success", label: "On" },
  off: { variant: "neutral", label: "Off" },
  given_up: { variant: "danger", label: "Stopped" },
} as const;

/** Where Plane tells the app that something happened, and the secret that proves a message came from Plane. */
export function EventsSection(props: Props) {
  const { app, onChanged, onReveal } = props;
  const { webhook } = app;
  const [address, setAddress] = useState(webhook.url);
  const [busy, setBusy] = useState<TBusy | null>(null);
  const [confirm, setConfirm] = useState<TConfirm>(null);

  const state = STATE_BADGE[webhook.state];
  const trimmed = address.trim();
  const hasAddress = webhook.url !== "";
  // After repeated failures the address is switched off; saving it again is how it is switched back on.
  const canSave = trimmed !== "" && (trimmed !== webhook.url || webhook.state === "given_up");

  const run = async (name: TBusy, failedTitle: string, action: () => Promise<void>) => {
    setBusy(name);
    try {
      await action();
    } catch (error) {
      showError(failedTitle, error);
    } finally {
      setBusy(null);
      setConfirm(null);
    }
  };

  const save = () =>
    run("save", "The address was not saved", async () => {
      const updated = await service.setEventsAddress(app.client_id, trimmed);
      setAddress(updated.webhook.url);
      onChanged(updated);
      setToast({ type: "success", title: "Address saved", message: "Plane will tell the app about events there." });
    });

  const turnOff = () =>
    run("off", "Events were not turned off", async () => {
      const updated = await service.turnEventsOff(app.client_id);
      setAddress("");
      onChanged(updated);
      setToast({ type: "success", title: "Events are off", message: "The app is no longer told about events." });
    });

  const sendTest = () =>
    run("test", "The test could not be sent", async () => {
      const result = await service.testEvents(app.client_id);
      setToast(
        result.heard
          ? { type: "success", title: "The app answered", message: result.detail }
          : { type: "error", title: "Not delivered", message: result.detail }
      );
    });

  const secretOf = (replace: boolean) =>
    run(replace ? "replace" : "show", "The signing secret could not be shown", async () => {
      const result = await service.eventsSecret(app.client_id, replace);
      onChanged(result.app);
      onReveal({
        title: replace ? "New signing secret" : "Signing secret",
        intro: replace
          ? "The old secret no longer matches. Give the app this one now, or it will refuse every message from Plane."
          : "The app uses this to check that a message really comes from Plane. You can show it again whenever you need it.",
        once: false,
        fields: [
          {
            label: "Signing secret",
            value: result.webhook_secret,
            description: "Sent with every message as a signature. Keep it as private as the client secret.",
          },
        ],
      });
    });

  return (
    <section className="space-y-3" aria-labelledby={`events-${app.client_id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h4 id={`events-${app.client_id}`} className="text-body-sm-medium text-primary">
          Events
        </h4>
        <Badge variant={state.variant} size="sm" label={state.label} />
      </div>
      <p className="text-body-xs-regular text-tertiary">
        Plane can tell the app when work is assigned to a person, a due date or state changes, or a connection ends, so
        it does not have to keep asking. Without an address the app has to ask on its own.
      </p>
      {webhook.state === "given_up" && (
        <p role="status" className="text-body-xs-regular text-danger-primary">
          Plane stopped sending on {formatMoment(webhook.disabled_at)}, after {webhook.failures} failed messages in a
          row. Fix the app, then save the address again to switch events back on.
        </p>
      )}
      <form
        className="flex flex-col gap-2 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSave && busy === null) void save();
        }}
      >
        <div className="min-w-0 flex-1">
          <InputField
            id={`events_address_${app.client_id}`}
            size="lg"
            orientation="vertical"
            label="Address to send events to"
            type="url"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            placeholder="https://bot.example.com/plane/events"
            hint="Must be https. Plane refuses addresses that point inside your own network, unless the server is set to allow that host."
            spellCheck={false}
            autoComplete="off"
          />
        </div>
        <Button
          type="submit"
          variant="primary"
          size="lg"
          stretch="auto"
          disabled={!canSave}
          loading={busy === "save"}
          label={webhook.state === "given_up" ? "Switch back on" : "Save address"}
        />
      </form>
      {hasAddress && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            onClick={() => void sendTest()}
            disabled={busy !== null}
            loading={busy === "test"}
            label="Send a test message"
          />
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            onClick={() => void secretOf(false)}
            disabled={busy !== null}
            loading={busy === "show"}
            label="Show signing secret"
          />
          <Button
            variant="ghost"
            size="md"
            stretch="auto"
            onClick={() => setConfirm("replace")}
            disabled={busy !== null}
            label="Replace signing secret"
          />
          <Button
            variant="ghost"
            size="md"
            stretch="auto"
            onClick={() => setConfirm("off")}
            disabled={busy !== null}
            label="Turn events off"
          />
        </div>
      )}
      <ConfirmDialog
        isOpen={confirm === "replace"}
        handleClose={() => setConfirm(null)}
        handleSubmit={() => secretOf(true)}
        isSubmitting={busy === "replace"}
        variant="warning"
        title="Replace the signing secret?"
        content="The old secret stops matching at once. Until the app has the new one it will refuse every message from Plane."
        primaryButtonText={{ default: "Replace secret", loading: "Replacing" }}
        secondaryButtonText="Keep the current one"
      />
      <ConfirmDialog
        isOpen={confirm === "off"}
        handleClose={() => setConfirm(null)}
        handleSubmit={turnOff}
        isSubmitting={busy === "off"}
        variant="warning"
        title="Turn events off?"
        content="The app will no longer be told about anything and has to ask on its own. The address is removed; you can enter it again later."
        primaryButtonText={{ default: "Turn off", loading: "Turning off" }}
        secondaryButtonText="Keep them on"
      />
    </section>
  );
}
