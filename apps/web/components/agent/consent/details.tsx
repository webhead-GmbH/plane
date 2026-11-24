/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
// plane imports
import { Badge } from "@makeplane/propel/components/badge";
import { useTranslation } from "@plane/i18n";
// services
import type { TAgentConsent, TAgentLinkedAccount, TAgentScope } from "@/services/agent-connection.service";
// local imports
import { handleLabel, providerLabel } from "../helpers";
import { useScopeText } from "../use-scope-text";

function Panel(props: { heading: string; headingId: string; children: ReactNode }) {
  const { heading, headingId, children } = props;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-body-sm-semibold text-primary">
        {heading}
      </h2>
      {children}
    </section>
  );
}

function Field(props: { label: string; children: ReactNode }) {
  const { label, children } = props;
  return (
    <div className="contents">
      <dt className="text-body-xs-regular text-tertiary">{label}</dt>
      <dd className="min-w-0 text-body-sm-medium break-words text-primary">{children}</dd>
    </div>
  );
}

/**
 * Who, on the app's side, is being linked. Every value here was typed by somebody else and handed
 * over by the app, so each is isolated with `<bdi>`: a Persian name next to an English handle, or a
 * name built from right-to-left controls, cannot reorder what is around it.
 */
function LinkedAccount(props: { account: TAgentLinkedAccount }) {
  const { account } = props;
  const { t } = useTranslation();
  const handle = handleLabel(account.username);

  return (
    <Panel heading={t("agent.consent.account_heading")} headingId="agent-consent-account">
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 rounded-lg border border-subtle bg-layer-1 p-3">
        <Field label={t("agent.consent.account_service")}>
          <bdi>{providerLabel(account.provider)}</bdi>
        </Field>
        {account.name && (
          <Field label={t("agent.consent.account_name")}>
            <bdi dir="auto">{account.name}</bdi>
          </Field>
        )}
        {handle && (
          <Field label={t("agent.consent.account_username")}>
            <bdi dir="auto">{handle}</bdi>
          </Field>
        )}
        <Field label={t("agent.consent.account_id")}>
          <bdi dir="ltr">{account.id}</bdi>
        </Field>
      </dl>
    </Panel>
  );
}

function PlaneAccount(props: { user: TAgentConsent["user"] }) {
  const { user } = props;
  const { t } = useTranslation();

  return (
    <Panel heading={t("agent.consent.plane_account_heading")} headingId="agent-consent-plane-account">
      <div className="flex flex-col gap-0.5 rounded-lg border border-subtle bg-layer-1 p-3">
        <span className="text-body-sm-medium break-words text-primary">
          <bdi dir="auto">{user.display_name}</bdi>
        </span>
        <span className="text-body-xs-regular break-all text-tertiary">
          <bdi dir="ltr">{user.email}</bdi>
        </span>
      </div>
      <p className="text-body-xs-regular text-tertiary">{t("agent.consent.plane_account_help")}</p>
    </Panel>
  );
}

function ScopeList(props: { scopes: TAgentScope[]; appName: string }) {
  const { scopes, appName } = props;
  const { t } = useTranslation();
  const scopeText = useScopeText();

  return (
    <Panel heading={t("agent.consent.scopes_heading", { app: appName })} headingId="agent-consent-scopes">
      <ul className="flex flex-col divide-y divide-subtle rounded-lg border border-subtle">
        {scopes.map((scope) => {
          const text = scopeText(scope);
          return (
            <li key={scope.id} className="flex flex-col gap-0.5 p-3">
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-body-sm-medium text-primary">{text.title}</span>
                {scope.writes && <Badge variant="warning" size="xs" label={t("agent.consent.can_change")} />}
                {scope.others && <Badge variant="warning" size="xs" label={t("agent.consent.sees_others")} />}
              </span>
              {text.description && <span className="text-body-xs-regular text-tertiary">{text.description}</span>}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

/** What the person is being asked to approve: who is linked, as which Plane account, and for what. */
export function ConsentDetails(props: { consent: TAgentConsent }) {
  const { consent } = props;

  return (
    <div className="flex flex-col gap-5">
      <LinkedAccount account={consent.account} />
      <PlaneAccount user={consent.user} />
      <ScopeList scopes={consent.scopes} appName={consent.client.name} />
    </div>
  );
}
