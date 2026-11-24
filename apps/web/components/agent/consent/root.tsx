/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import useSWR from "swr";
// plane imports
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import { EmptyStateDetailed } from "@plane/blocks/empty-state";
import { PlaneLogo } from "@plane/blocks/icons";
import { useTranslation } from "@plane/i18n";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
import { PageHead } from "@/components/core/page-title";
// hooks
import { useAppRouter } from "@/hooks/use-app-router";
// services
import { AgentConnectionService } from "@/services/agent-connection.service";
import type { TAgentConsent, TAgentError } from "@/services/agent-connection.service";
// local imports
import { safeRedirectUrl } from "../helpers";
import { ConsentDetails } from "./details";

const agentConnectionService = new AgentConnectionService();

type TDecision = "approve" | "deny";
type TFailure = "expired" | "failed";

/**
 * Whether this page is inside another page. The web app is served apart from the API, so the API's
 * frame protection does not cover it: a page that frames this one and lines a decoy up over "Allow"
 * could have a person approve something they never saw. Comparing `window.top` to `window.self` is
 * allowed across origins, and is all that is needed to refuse.
 */
function isInsideFrame(): boolean {
  try {
    return window.top !== window.self;
  } catch {
    return true;
  }
}

// Nothing to subscribe to: whether a page is framed does not change while it is open.
const subscribeToNothing = () => () => {};

function errorCode(error: unknown): string | undefined {
  return (error as TAgentError | undefined)?.error;
}

function Shell(props: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center bg-canvas px-4 py-10 sm:py-16">
      <PlaneLogo className="h-8 w-auto text-primary" />
      <main className="mt-8 w-full max-w-lg">{props.children}</main>
    </div>
  );
}

function StateScreen(props: {
  assetKey: "invalid-link" | "server-error" | "no-access";
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
}) {
  const { assetKey, title, description, actionLabel, onAction } = props;
  return (
    <EmptyStateDetailed
      align="center"
      assetKey={assetKey}
      assetClassName="size-40"
      title={title}
      description={description}
      actions={[{ label: actionLabel, variant: "primary", onClick: onAction }]}
    />
  );
}

export function AgentConsentRoot(props: { requestToken: string }) {
  const { requestToken } = props;
  // states
  const [pending, setPending] = useState<TDecision | null>(null);
  const [failure, setFailure] = useState<TFailure | null>(null);
  const [returnTo, setReturnTo] = useState<string | null>(null);
  // refs
  const headingRef = useRef<HTMLHeadingElement>(null);
  // router
  const router = useAppRouter();
  // Read as an external value, so that nothing is decided from the browser's globals during render.
  const isFramed = useSyncExternalStore(subscribeToNothing, isInsideFrame, () => false);
  // translation
  const { t } = useTranslation();
  // The request is not fetched at all inside a frame: the answer carries the value an approval needs.
  const {
    data: consent,
    error,
    isLoading,
    mutate,
  } = useSWR<TAgentConsent>(
    isFramed ? null : `AGENT_CONSENT_${requestToken}`,
    () => agentConnectionService.getConsent(requestToken),
    { revalidateOnFocus: false, revalidateOnReconnect: false, shouldRetryOnError: false }
  );

  // The heading is what a screen reader should start from, and what a keyboard user lands on.
  useEffect(() => {
    if (consent) headingRef.current?.focus();
  }, [consent]);

  const decide = async (decision: TDecision) => {
    if (!consent || pending) return;
    setPending(decision);
    try {
      const answer =
        decision === "approve"
          ? await agentConnectionService.approve(requestToken, consent.nonce)
          : await agentConnectionService.deny(requestToken, consent.nonce);
      const target = safeRedirectUrl(answer?.redirect_to);
      if (!target) {
        setFailure("failed");
        setPending(null);
        return;
      }
      // Buttons stay off from here: the browser is on its way and a second press would be refused anyway.
      setReturnTo(target);
      window.location.assign(target);
    } catch (decisionError) {
      setFailure(errorCode(decisionError) === "not_found" ? "expired" : "failed");
      setPending(null);
    }
  };

  const retry = () => {
    setFailure(null);
    void mutate();
  };

  const goHome = () => router.push("/");

  if (isFramed) {
    return (
      <Shell>
        <PageHead title={t("agent.consent.page_title")} />
        <StateScreen
          assetKey="no-access"
          title={t("agent.consent.framed_title")}
          description={t("agent.consent.framed_description")}
          actionLabel={t("agent.consent.framed_open")}
          onAction={() => window.open(window.location.href, "_blank", "noopener,noreferrer")}
        />
      </Shell>
    );
  }

  if (failure === "expired" || (!consent && errorCode(error) === "not_found")) {
    return (
      <Shell>
        <PageHead title={t("agent.consent.page_title")} />
        <StateScreen
          assetKey="invalid-link"
          title={t("agent.consent.expired_title")}
          description={t("agent.consent.expired_description")}
          actionLabel={t("go_home")}
          onAction={goHome}
        />
      </Shell>
    );
  }

  if (failure === "failed" || (!consent && error)) {
    return (
      <Shell>
        <PageHead title={t("agent.consent.page_title")} />
        <StateScreen
          assetKey="server-error"
          title={t("agent.consent.error_title")}
          description={t("agent.consent.error_description")}
          actionLabel={t("common.retry")}
          onAction={retry}
        />
      </Shell>
    );
  }

  if (isLoading || !consent) {
    return (
      <div className="grid min-h-screen place-items-center">
        <LogoSpinner />
      </div>
    );
  }

  const appName = consent.client.name;

  return (
    <Shell>
      <PageHead title={t("agent.consent.page_title")} />
      <div className="flex flex-col gap-6 rounded-lg border border-subtle bg-surface-1 p-6 sm:p-8">
        <div className="flex flex-col gap-2">
          <h1 ref={headingRef} tabIndex={-1} className="text-h5-semibold text-primary outline-none">
            {t("agent.consent.title", { app: appName })}
          </h1>
          {consent.client.description && (
            <p className="text-body-sm-regular text-secondary">{consent.client.description}</p>
          )}
          <p className="text-body-sm-regular text-tertiary">{t("agent.consent.description", { app: appName })}</p>
        </div>

        <Banner
          role="note"
          placement="inline"
          variant="warning"
          title={t("agent.consent.warning_title")}
          description={t("agent.consent.warning_description", { app: appName })}
        />

        <ConsentDetails consent={consent} />

        {returnTo ? (
          <p role="status" className="text-body-sm-regular text-secondary">
            {t("agent.consent.redirecting", { app: appName })}{" "}
            <a className="text-accent-primary underline" href={returnTo} rel="noopener noreferrer">
              {t("agent.consent.continue")}
            </a>
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="primary"
                size="md"
                stretch="auto"
                label={t("agent.consent.allow")}
                loading={pending === "approve"}
                disabled={pending !== null}
                onClick={() => decide("approve")}
              />
              <Button
                variant="secondary"
                size="md"
                stretch="auto"
                label={t("common.cancel")}
                loading={pending === "deny"}
                disabled={pending !== null}
                onClick={() => decide("deny")}
              />
            </div>
            <p className="text-body-xs-regular text-tertiary">{t("agent.consent.revoke_hint")}</p>
          </div>
        )}
      </div>
    </Shell>
  );
}
