/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Skeleton } from "@plane/blocks/skeleton";
import { InstanceAgentAppService } from "@plane/services";
import type { TAgentApp } from "@plane/types";
// components
import { PageWrapper } from "@/components/common/page-wrapper";
// types
import type { Route } from "./+types/page";
// local
import { AppCard } from "./app-card";
import { AppFormDialog } from "./app-form-dialog";
import type { TRevealed } from "./helpers";
import { RevealDialog } from "./reveal-dialog";

const service = new InstanceAgentAppService();

/** Where an administrator registers the apps people may connect to their Plane account, and looks after them. */
export default function ConnectedAppsPage(_props: Route.ComponentProps) {
  const { data, error, isLoading, mutate } = useSWR("AGENT_APPS", () => service.list(), {
    revalidateOnFocus: false,
  });
  // The dialog for adding (no app) or changing an app. The app stays put while the dialog fades out.
  const [formOpen, setFormOpen] = useState(false);
  const [formApp, setFormApp] = useState<TAgentApp | null>(null);
  const [revealed, setRevealed] = useState<TRevealed | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const apps = data?.apps ?? [];

  const openForm = (app: TAgentApp | null) => {
    setFormApp(app);
    setFormOpen(true);
  };

  // An action answered with the app as it is now: use that instead of asking for the whole list again.
  const replaceApp = (updated: TAgentApp) =>
    mutate(
      (current) =>
        current && {
          ...current,
          apps: current.apps.map((app) => (app.client_id === updated.client_id ? updated : app)),
        },
      { revalidate: false }
    );

  const handleSaved = async ({ app, clientSecret }: { app: TAgentApp; clientSecret?: string }) => {
    await mutate();
    setFormOpen(false);
    if (clientSecret) {
      setOpenId(app.client_id);
      setRevealed({
        title: `${app.name} is added`,
        intro: `Give ${app.name} these two values in its own settings. It uses them to prove to Plane that it is the app.`,
        once: true,
        fields: [
          {
            label: "Client ID",
            value: app.client_id,
            description: "Not a secret. The app sends it with every request.",
          },
          {
            label: "Client secret",
            value: clientSecret,
            description: "How the app proves to Plane that it is the app. Keep it as private as a password.",
          },
        ],
      });
    }
  };

  return (
    <PageWrapper
      header={{
        title: "Connected apps",
        description:
          "Register the apps, such as a chat bot, that people may connect to their own Plane account. Plane makes the app's ID and secret, which you give to the app. Nothing is connected until a person approves it.",
        actions: (
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            onClick={() => openForm(null)}
            disabled={!data}
            label="Add app"
          />
        ),
      }}
    >
      {isLoading ? (
        <Skeleton className="space-y-4">
          <Skeleton.Item height="88px" width="100%" />
          <Skeleton.Item height="88px" width="100%" />
        </Skeleton>
      ) : error || !data ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-subtle p-4">
          <p role="alert" className="text-body-sm-regular text-danger-primary">
            The apps could not be loaded.
          </p>
          <Button variant="secondary" size="md" stretch="auto" onClick={() => void mutate()} label="Try again" />
        </div>
      ) : apps.length === 0 ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-subtle p-6">
          <h3 className="text-body-md-medium text-primary">No apps yet</h3>
          <p className="max-w-xl text-body-sm-regular text-secondary">
            Add an app to let people connect it to their Plane account, for example a chat bot that reminds them to log
            their time. You choose what it may ask for, and each person decides whether to connect it.
          </p>
          <Button variant="primary" size="md" stretch="auto" onClick={() => openForm(null)} label="Add app" />
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {apps.map((app) => (
            <AppCard
              key={app.client_id}
              app={app}
              scopes={data.scopes}
              isOpen={openId === app.client_id}
              onToggle={() => setOpenId(openId === app.client_id ? null : app.client_id)}
              onEdit={() => openForm(app)}
              onChanged={(updated) => void replaceApp(updated)}
              onReveal={setRevealed}
            />
          ))}
        </div>
      )}
      <AppFormDialog
        isOpen={formOpen}
        app={formApp}
        scopes={data?.scopes ?? []}
        defaultScopes={data?.default_scopes ?? []}
        onClose={() => setFormOpen(false)}
        onSaved={handleSaved}
      />
      <RevealDialog revealed={revealed} onClose={() => setRevealed(null)} />
    </PageWrapper>
  );
}

export const meta: Route.MetaFunction = () => [{ title: "Connected apps - God Mode" }];
