/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { CheckCircle2, Copy } from "lucide-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { copyTextToClipboard, renderFormattedDate } from "@plane/utils";
// services
import { GoogleDriveService } from "@/services/google-drive.service";
import type { TDriveConnection } from "@/services/google-drive.service";
// local imports
import { I18N, driveErrorMessage } from "./errors";

const driveService = new GoogleDriveService();

const SETUP_STEPS = ["enable_api", "consent_screen", "create_client", "redirect_uri", "paste"] as const;

type TProps = {
  workspaceSlug: string;
  connection: TDriveConnection;
  onChange: (connection: TDriveConnection) => void;
};

/**
 * The Google client this workspace signs in with, and the account it signed in as.
 *
 * Each company brings its own Google Cloud client, so the files stay between it
 * and Google: the steps to make one are on the page, with the redirect address
 * ready to copy.
 */
export const DriveConnectionSection = ({ workspaceSlug, connection, onChange }: TProps) => {
  const { t } = useTranslation();
  // What the admin typed, until it is saved; the saved client otherwise.
  const [typedClientId, setTypedClientId] = useState<string | null>(null);
  const clientId = typedClientId ?? connection.client_id;
  const [clientSecret, setClientSecret] = useState("");
  const [isConnecting, setIsConnecting] = useState(false);
  const [isConfirmingDisconnect, setIsConfirmingDisconnect] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  const clientChanged = clientId.trim() !== connection.client_id || clientSecret.trim() !== "";
  const canConnect = Boolean(clientId.trim()) && (connection.has_client_secret || Boolean(clientSecret.trim()));

  const copyRedirectUri = () =>
    void copyTextToClipboard(connection.redirect_uri).then(() =>
      setToast({ type: "success", title: t(`${I18N}.connection.redirect_copied`) })
    );

  const connect = async () => {
    setIsConnecting(true);
    try {
      if (clientChanged) {
        onChange(
          await driveService.updateConnection(workspaceSlug, {
            client_id: clientId.trim(),
            ...(clientSecret.trim() ? { client_secret: clientSecret.trim() } : {}),
          })
        );
        setTypedClientId(null);
        setClientSecret("");
      }
      // Off to Google; it sends the admin back to this page with the outcome in the address.
      window.location.assign(await driveService.authorizationUrl(workspaceSlug));
    } catch (failure) {
      setIsConnecting(false);
      setToast({
        type: "error",
        title: t(`${I18N}.connection.connect_failed`),
        message: driveErrorMessage(failure, t),
      });
    }
  };

  const disconnect = async () => {
    setIsDisconnecting(true);
    try {
      onChange(await driveService.disconnect(workspaceSlug));
      setToast({ type: "success", title: t(`${I18N}.connection.disconnected`) });
    } catch (failure) {
      setToast({
        type: "error",
        title: t(`${I18N}.connection.disconnect_failed`),
        message: driveErrorMessage(failure, t),
      });
    } finally {
      setIsDisconnecting(false);
      setIsConfirmingDisconnect(false);
    }
  };

  return (
    <section className="flex flex-col gap-4" aria-labelledby="gdrive-connection-heading">
      <div className="flex flex-col gap-1">
        <h3 id="gdrive-connection-heading" className="text-body-md-medium text-primary">
          {t(`${I18N}.connection.heading`)}
        </h3>
        {connection.connected ? (
          <p className="flex items-center gap-1.5 text-body-sm-regular text-secondary">
            <CheckCircle2 className="size-4 shrink-0 text-success-primary" aria-hidden />
            {t(`${I18N}.connection.connected_as`, {
              email: connection.account_email || "—",
              date: connection.connected_at ? renderFormattedDate(connection.connected_at) : "—",
            })}
          </p>
        ) : (
          <p className="text-body-sm-regular text-tertiary">{t(`${I18N}.connection.not_connected`)}</p>
        )}
      </div>

      {!connection.connected && (
        <ol className="flex list-decimal flex-col gap-1.5 ps-5 text-body-sm-regular text-secondary">
          {SETUP_STEPS.map((step) => (
            <li key={step}>{t(`${I18N}.connection.steps.${step}`)}</li>
          ))}
        </ol>
      )}

      <div className="flex flex-col gap-1">
        <span id="gdrive-redirect-label" className="text-body-sm-medium text-secondary">
          {t(`${I18N}.connection.redirect_uri`)}
        </span>
        <div className="flex items-center gap-2">
          <code
            aria-labelledby="gdrive-redirect-label"
            className="min-w-0 grow truncate rounded-md border border-subtle bg-layer-1 px-3 py-2 text-body-xs-regular text-primary"
          >
            {connection.redirect_uri}
          </code>
          <Tooltip label={t(`${I18N}.connection.copy`)}>
            <IconButton
              variant="secondary"
              size="lg"
              icon={<Icon icon={Copy} />}
              aria-label={t(`${I18N}.connection.copy`)}
              onClick={copyRedirectUri}
            />
          </Tooltip>
        </div>
        <p className="text-body-xs-regular text-tertiary">{t(`${I18N}.connection.redirect_uri_help`)}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="gdrive-client-id" className="text-body-sm-medium text-secondary">
            {t(`${I18N}.connection.client_id`)}
          </label>
          <InputGroup size="xl">
            <Input
              size="xl"
              id="gdrive-client-id"
              autoComplete="off"
              spellCheck={false}
              value={clientId}
              onChange={(event) => setTypedClientId(event.target.value)}
              placeholder="1234567890-abc.apps.googleusercontent.com"
            />
          </InputGroup>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="gdrive-client-secret" className="text-body-sm-medium text-secondary">
            {t(`${I18N}.connection.client_secret`)}
          </label>
          <InputGroup size="xl">
            <Input
              size="xl"
              id="gdrive-client-secret"
              type="password"
              autoComplete="off"
              value={clientSecret}
              onChange={(event) => setClientSecret(event.target.value)}
              placeholder={
                connection.has_client_secret
                  ? t(`${I18N}.connection.client_secret_set`)
                  : t(`${I18N}.connection.client_secret_placeholder`)
              }
            />
          </InputGroup>
        </div>
      </div>
      {connection.connected && clientId.trim() !== connection.client_id && (
        <p className="text-body-xs-regular text-warning-primary">{t(`${I18N}.connection.client_change_warning`)}</p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          size="sm"
          stretch="auto"
          label={connection.connected ? t(`${I18N}.connection.reconnect`) : t(`${I18N}.connection.connect`)}
          onClick={() => void connect()}
          loading={isConnecting}
          disabled={!canConnect}
        />
        {connection.connected && (
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={t(`${I18N}.connection.disconnect`)}
            onClick={() => setIsConfirmingDisconnect(true)}
          />
        )}
      </div>

      <ConfirmDialog
        isOpen={isConfirmingDisconnect}
        handleClose={() => setIsConfirmingDisconnect(false)}
        handleSubmit={() => void disconnect()}
        isSubmitting={isDisconnecting}
        variant="danger"
        title={t(`${I18N}.connection.disconnect_title`)}
        content={t(`${I18N}.connection.disconnect_body`)}
        primaryButtonText={{
          default: t(`${I18N}.connection.disconnect`),
          loading: t(`${I18N}.connection.disconnecting`),
        }}
        secondaryButtonText={t("common.cancel")}
      />
    </section>
  );
};
