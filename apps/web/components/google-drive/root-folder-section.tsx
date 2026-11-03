/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { ExternalLink, FolderTree } from "lucide-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
// services
import { GoogleDriveService } from "@/services/google-drive.service";
import type { TDriveConnection, TDriveConnectionPayload } from "@/services/google-drive.service";
// local imports
import { I18N, driveErrorMessage } from "./errors";
import { DriveFolderBrowser } from "./folder-browser";

const driveService = new GoogleDriveService();

type TProps = {
  workspaceSlug: string;
  connection: TDriveConnection;
  onChange: (connection: TDriveConnection) => void;
};

/**
 * The folder the project folders are in, such as "projects / webhead", so that
 * choosing a project's folder shows those and not the whole of Drive. It can be
 * walked to, or a link to it pasted from Drive.
 */
export const DriveRootFolderSection = ({ workspaceSlug, connection, onChange }: TProps) => {
  const { t } = useTranslation();
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [pasted, setPasted] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const root = connection.root_folder;

  const save = async (payload: TDriveConnectionPayload, success?: string) => {
    setIsSaving(true);
    try {
      onChange(await driveService.updateConnection(workspaceSlug, payload));
      if (success) setToast({ type: "success", title: success });
      return true;
    } catch (failure) {
      setToast({ type: "error", title: t(`${I18N}.root.save_failed`), message: driveErrorMessage(failure, t) });
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  const applyPasted = async () => {
    if (await save({ root_folder: pasted.trim() }, t(`${I18N}.root.saved`))) setPasted("");
  };

  return (
    <section className="flex flex-col gap-4 border-t border-subtle pt-6" aria-labelledby="gdrive-root-heading">
      <div className="flex flex-col gap-1">
        <h3 id="gdrive-root-heading" className="text-body-md-medium text-primary">
          {t(`${I18N}.root.heading`)}
        </h3>
        <p className="text-body-sm-regular text-tertiary">{t(`${I18N}.root.description`)}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-md border border-subtle bg-layer-1 px-4 py-3">
        <FolderTree className="size-4 shrink-0 text-tertiary" aria-hidden />
        <div className="flex min-w-0 grow flex-col">
          {root ? (
            <>
              <span className="truncate text-body-sm-medium text-primary">{root.path || root.name}</span>
              {root.url && (
                <a
                  href={root.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex w-fit items-center gap-1 text-body-xs-regular text-accent-primary hover:underline"
                >
                  {t(`${I18N}.root.open_in_drive`)}
                  <ExternalLink className="size-3" aria-hidden />
                </a>
              )}
            </>
          ) : (
            <span className="text-body-sm-regular text-tertiary">{t(`${I18N}.root.none`)}</span>
          )}
        </div>
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={root ? t(`${I18N}.root.change`) : t(`${I18N}.root.choose`)}
          onClick={() => setIsBrowsing(true)}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="gdrive-root-link" className="text-body-sm-medium text-secondary">
          {t(`${I18N}.root.paste_label`)}
        </label>
        <div className="flex items-center gap-2">
          <div className="min-w-0 grow">
            <InputGroup size="xl">
              <Input
                size="xl"
                id="gdrive-root-link"
                type="url"
                spellCheck={false}
                value={pasted}
                onChange={(event) => setPasted(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && pasted.trim()) void applyPasted();
                }}
                placeholder="https://drive.google.com/drive/folders/…"
              />
            </InputGroup>
          </div>
          <Button
            variant="secondary"
            size="lg"
            stretch="auto"
            label={t(`${I18N}.root.use_link`)}
            onClick={() => void applyPasted()}
            disabled={!pasted.trim()}
            loading={isSaving && Boolean(pasted.trim())}
          />
        </div>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <span id="gdrive-auto-link-label" className="text-body-sm-medium text-secondary">
            {t(`${I18N}.root.auto_link`)}
          </span>
          <p className="text-body-xs-regular text-tertiary">{t(`${I18N}.root.auto_link_help`)}</p>
        </div>
        <Switch
          size="sm"
          aria-labelledby="gdrive-auto-link-label"
          checked={connection.auto_link_new_projects}
          disabled={isSaving}
          onCheckedChange={(checked) => void save({ auto_link_new_projects: checked })}
        />
      </div>

      <DriveFolderBrowser
        workspaceSlug={workspaceSlug}
        isOpen={isBrowsing}
        onClose={() => setIsBrowsing(false)}
        onChoose={(folderId) => void save({ root_folder: folderId }, t(`${I18N}.root.saved`))}
      />
    </section>
  );
};
