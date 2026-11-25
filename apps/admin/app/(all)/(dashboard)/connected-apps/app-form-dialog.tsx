/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { InstanceAgentAppService } from "@plane/services";
import type { TAgentApp, TAgentScope, TAgentAppWithSecret } from "@plane/types";
// local
import { errorMessage, parseLines } from "./helpers";
import { ScopePicker } from "./scope-picker";

const service = new InstanceAgentAppService();

type Props = {
  isOpen: boolean;
  /** The app being changed; none when a new one is being added. */
  app: TAgentApp | null;
  scopes: TAgentScope[];
  defaultScopes: string[];
  onClose: () => void;
  /** An app was added (with its secret, shown once) or changed (without one). */
  onSaved: (result: { app: TAgentApp; clientSecret?: string }) => void | Promise<void>;
};

type TForm = { name: string; description: string; redirectUris: string; scopes: string[] };

const blankForm = (defaultScopes: string[]): TForm => ({
  name: "",
  description: "",
  redirectUris: "",
  scopes: defaultScopes,
});

const formOf = (app: TAgentApp): TForm => ({
  name: app.name,
  description: app.description,
  redirectUris: app.redirect_uris.join("\n"),
  scopes: app.allowed_scopes,
});

type TBodyProps = Omit<Props, "isOpen"> & {
  isSubmitting: boolean;
  onSubmittingChange: (isSubmitting: boolean) => void;
};

/** The form itself. It is mounted anew each time the dialog opens, so it starts from what the app is now. */
function AppFormBody(props: TBodyProps) {
  const { app, scopes, defaultScopes, onClose, onSaved, isSubmitting, onSubmittingChange } = props;
  const [form, setForm] = useState<TForm>(() => (app ? formOf(app) : blankForm(defaultScopes)));
  const [error, setError] = useState("");

  const isEditing = app !== null;
  const canSubmit = form.name.trim() !== "" && parseLines(form.redirectUris).length > 0 && form.scopes.length > 0;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit || isSubmitting) return;
    onSubmittingChange(true);
    setError("");
    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      redirect_uris: parseLines(form.redirectUris),
      allowed_scopes: form.scopes,
    };
    try {
      if (app) {
        await onSaved({ app: await service.update(app.client_id, payload) });
      } else {
        const created: TAgentAppWithSecret = await service.create(payload);
        await onSaved({ app: created.app, clientSecret: created.client_secret });
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      onSubmittingChange(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
      <DialogMain>
        <DialogHeader>
          <DialogHeading>
            <DialogTitle>{isEditing ? `Edit ${app.name}` : "Add an app"}</DialogTitle>
          </DialogHeading>
        </DialogHeader>
        <DialogBody>
          <div className="flex flex-col gap-5">
            <InputField
              id="agent_app_name"
              size="lg"
              orientation="vertical"
              label="Name"
              required
              description="People see this name when they are asked to connect the app."
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              maxLength={120}
              autoComplete="off"
            />
            <TextAreaField
              id="agent_app_description"
              size="lg"
              label="What it does"
              description="Optional. For your own notes."
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              maxLength={1000}
              rows={2}
            />
            <TextAreaField
              id="agent_app_redirect_uris"
              size="lg"
              label="Redirect addresses"
              required
              description="One per line. After a person approves, Plane sends them back to one of these, so use the full callback address from the app's own settings. Must be https (plain http only for localhost)."
              value={form.redirectUris}
              onChange={(event) => setForm({ ...form, redirectUris: event.target.value })}
              placeholder="https://bot.example.com/plane/callback"
              rows={3}
              spellCheck={false}
              autoCapitalize="off"
            />
            <ScopePicker
              scopes={scopes}
              selected={form.scopes}
              onChange={(next) => setForm({ ...form, scopes: next })}
            />
            {isEditing && (
              <p className="text-body-xs-regular text-tertiary">
                People who have already connected the app keep what they agreed to. To take it away from them, end their
                connections on the app&apos;s page.
              </p>
            )}
            {error && (
              <p role="alert" className="text-body-sm-regular text-danger-primary">
                {error}
              </p>
            )}
          </div>
        </DialogBody>
      </DialogMain>
      <DialogActions>
        <Button variant="secondary" size="md" stretch="auto" onClick={onClose} disabled={isSubmitting} label="Cancel" />
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          type="submit"
          disabled={!canSubmit}
          loading={isSubmitting}
          label={isEditing ? "Save changes" : "Add app"}
        />
      </DialogActions>
    </form>
  );
}

/** Adding an app, or changing what one is called, where people are sent back to, and what it may ask for. */
export function AppFormDialog(props: Props) {
  const { isOpen, onClose, ...rest } = props;
  const [isSubmitting, setIsSubmitting] = useState(false);

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !isSubmitting) onClose();
      }}
    >
      <DialogContent size="lg">
        <AppFormBody
          key={isOpen ? "open" : "closed"}
          {...rest}
          onClose={onClose}
          isSubmitting={isSubmitting}
          onSubmittingChange={setIsSubmitting}
        />
      </DialogContent>
    </Dialog>
  );
}
