/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { ChevronRight, Folder, HardDrive, Users } from "lucide-react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Dialog, DialogContent, DialogTitle } from "@makeplane/propel/components/dialog";
import { useTranslation } from "@plane/i18n";
import { Loader } from "@plane/blocks/skeleton";
// services
import { GoogleDriveService } from "@/services/google-drive.service";
import type { TDriveBrowseItem, TDriveFolderRef } from "@/services/google-drive.service";
// local imports
import { I18N, driveErrorMessage } from "./errors";

const driveService = new GoogleDriveService();

type TProps = {
  workspaceSlug: string;
  /** A folder to start in and stay inside, such as the projects folder. Without it, all of Drive. */
  within?: TDriveFolderRef;
  isOpen: boolean;
  onClose: () => void;
  onChoose: (folderId: string) => void;
};

const ICONS = { my_drive: HardDrive, shared_with_me: Users, shared_drive: HardDrive, folder: Folder };

/**
 * Walking down Drive one folder at a time to the one the project folders are in.
 *
 * The top level is My Drive, Shared with me and each shared drive, because a
 * company's project folders are as likely to be in a shared drive as in one
 * person's Drive. Given a folder to stay inside, the top is that folder instead.
 */
export const DriveFolderBrowser = ({ workspaceSlug, within, isOpen, onClose, onChoose }: TProps) => {
  const { t } = useTranslation();
  // The trail from the top down to the folder being looked into.
  const [trail, setTrail] = useState<TDriveBrowseItem[]>([]);
  const current = trail[trail.length - 1];
  const parent = current?.id ?? within?.id ?? "";
  const { data, error, isLoading } = useSWR(isOpen ? ["GDRIVE_FOLDERS", workspaceSlug, parent] : null, () =>
    driveService.folders(workspaceSlug, parent)
  );
  // "Shared with me" is a list, not a folder, so there is nothing to choose while in it; nor
  // is the folder being stayed inside, which holds the choices rather than being one.
  const canChoose = Boolean(current) && current.kind !== "shared_with_me";

  const close = () => {
    setTrail([]);
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => (!open ? close() : undefined)}>
      <DialogContent size="md">
        <div className="flex max-h-[80vh] flex-col gap-4 p-5">
          <DialogTitle>{t(`${I18N}.browser.title`)}</DialogTitle>

          <nav aria-label={t(`${I18N}.browser.top`)} className="flex flex-wrap items-center gap-1 text-13">
            <button
              type="button"
              className={trail.length ? "text-secondary hover:text-primary" : "font-medium text-primary"}
              onClick={() => setTrail([])}
            >
              {within?.name ?? t(`${I18N}.browser.top`)}
            </button>
            {trail.map((item, index) => (
              <span key={item.id} className="flex items-center gap-1">
                <ChevronRight className="size-3 text-tertiary" aria-hidden />
                <button
                  type="button"
                  className={
                    index === trail.length - 1 ? "font-medium text-primary" : "text-secondary hover:text-primary"
                  }
                  onClick={() => setTrail(trail.slice(0, index + 1))}
                >
                  {item.name}
                </button>
              </span>
            ))}
          </nav>

          <div className="min-h-48 overflow-y-auto rounded-md border border-subtle">
            {isLoading ? (
              <Loader className="flex flex-col gap-1 p-2">
                <Loader.Item height="32px" />
                <Loader.Item height="32px" />
                <Loader.Item height="32px" />
              </Loader>
            ) : error ? (
              <p className="p-4 text-13 text-danger-primary">{driveErrorMessage(error, t)}</p>
            ) : (data ?? []).length === 0 ? (
              <p className="p-4 text-13 text-tertiary">{t(`${I18N}.browser.empty`)}</p>
            ) : (
              <ul>
                {(data ?? []).map((item) => {
                  const ItemIcon = ICONS[item.kind];
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-13 text-primary hover:bg-layer-transparent-hover"
                        onClick={() => setTrail([...trail, item])}
                        aria-label={t(`${I18N}.browser.open`, { name: item.name })}
                      >
                        <ItemIcon className="size-4 shrink-0 text-tertiary" aria-hidden />
                        <span className="min-w-0 grow truncate">{item.name}</span>
                        <ChevronRight className="size-4 shrink-0 text-tertiary" aria-hidden />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button variant="secondary" size="md" stretch="auto" label={t(`${I18N}.browser.cancel`)} onClick={close} />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              label={t(`${I18N}.browser.use_this`)}
              disabled={!canChoose}
              onClick={() => {
                if (!current) return;
                onChoose(current.id);
                close();
              }}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
