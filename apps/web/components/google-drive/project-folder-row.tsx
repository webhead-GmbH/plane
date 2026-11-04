/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { ExternalLink, Folder, FolderPlus, FolderSearch } from "lucide-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { MoreHorizontalOutline } from "@makeplane/propel/icons";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// services
import { GoogleDriveService } from "@/services/google-drive.service";
import type { TDriveFolderRef, TDriveProjectRow } from "@/services/google-drive.service";
// local imports
import { I18N, driveErrorMessage } from "./errors";
import { DriveFolderBrowser } from "./folder-browser";

const driveService = new GoogleDriveService();

type TFolderOption = { id: string; name: string; score?: number };

type TProps = {
  workspaceSlug: string;
  row: TDriveProjectRow;
  /** Every folder in the projects folder, to choose from. */
  folders: { id: string; name: string }[];
  /** The projects folder: choosing from Drive starts there and stays inside it. */
  rootFolder: TDriveFolderRef;
  onChange: () => void;
};

/** One project and its folder: linked, or the folders that look like its own and the means to pick one. */
export const DriveProjectFolderRow = ({ workspaceSlug, row, folders, rootFolder, onChange }: TProps) => {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const { project, folder, suggestions } = row;
  const clear = suggestions.find((suggestion) => suggestion.clear);

  const run = async (change: () => Promise<unknown>, success: string) => {
    setIsSaving(true);
    try {
      await change();
      setIsEditing(false);
      setToast({ type: "success", title: success });
      onChange();
    } catch (failure) {
      setToast({ type: "error", title: t(`${I18N}.projects.save_failed`), message: driveErrorMessage(failure, t) });
    } finally {
      setIsSaving(false);
    }
  };

  const link = (folderId: string) =>
    void run(
      () => driveService.setProjectFolder(workspaceSlug, project.id, { folder_id: folderId }),
      t(`${I18N}.projects.linked`, { project: project.name })
    );
  const create = () =>
    void run(
      () => driveService.setProjectFolder(workspaceSlug, project.id, { create: true }),
      t(`${I18N}.projects.created`, { project: project.name })
    );
  const unlink = () =>
    void run(
      () => driveService.unlinkProject(workspaceSlug, project.id),
      t(`${I18N}.projects.unlinked`, { project: project.name })
    );

  // The folders that look like this project's first, then all the others.
  const suggested: TFolderOption[] = suggestions.map(({ id, name, score }) => ({ id, name, score }));
  const options: TFolderOption[] = [
    ...suggested,
    ...folders.filter((item) => !suggestions.some((suggestion) => suggestion.id === item.id)),
  ];
  const groupLabel = (option: TFolderOption) =>
    option.score === undefined ? t(`${I18N}.projects.all_folders`) : t(`${I18N}.projects.suggested`);

  return (
    <li className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:gap-4">
      <div className="flex min-w-0 items-center gap-2 md:w-2/5">
        <span className="shrink-0 rounded-sm bg-layer-2 px-1.5 py-0.5 text-caption-sm-medium text-tertiary">
          {project.identifier}
        </span>
        <span className="truncate text-body-sm-medium text-primary">{project.name}</span>
      </div>

      {/* A linked row stays on one line and shortens the folder name; the choosing controls may wrap. */}
      <div
        className={cn(
          "flex min-w-0 grow items-center justify-end gap-2",
          folder && !isEditing ? "flex-nowrap" : "flex-wrap"
        )}
      >
        {folder && !isEditing ? (
          <>
            <a
              href={folder.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex min-w-0 grow items-center gap-1.5 text-body-sm-regular text-primary hover:underline"
            >
              <Folder className="size-4 shrink-0 text-tertiary" aria-hidden />
              <span className="truncate">{folder.name}</span>
              <ExternalLink className="size-3 shrink-0 text-tertiary" aria-hidden />
            </a>
            <span className="shrink-0 text-body-xs-regular text-tertiary">
              {t(`${I18N}.projects.method.${folder.method}`)}
            </span>
            <Menu>
              <MenuTrigger
                render={
                  <IconButton
                    variant="ghost"
                    size="sm"
                    aria-label={t(`${I18N}.projects.actions`, { project: project.name })}
                    icon={<Icon icon={MoreHorizontalOutline} />}
                    loading={isSaving}
                  />
                }
              />
              <MenuContent align="end">
                <MenuItem label={t(`${I18N}.projects.change`)} onClick={() => setIsEditing(true)} />
                <MenuItem label={t(`${I18N}.projects.unlink`)} onClick={unlink} />
              </MenuContent>
            </Menu>
          </>
        ) : (
          <>
            {clear && !folder && (
              <Button
                variant="secondary"
                size="sm"
                stretch="auto"
                label={t(`${I18N}.projects.use_suggestion`, { name: clear.name })}
                onClick={() => link(clear.id)}
                disabled={isSaving}
              />
            )}
            <div className="min-w-0 grow md:max-w-72">
              <Select<TFolderOption>
                getValues={() => options}
                value={null}
                onChange={(folderId) => link(folderId)}
                getOptionValue={(option) => option.id}
                getOptionLabel={(option) => option.name}
                getOptionIcon={() => <Folder className="size-3.5 text-tertiary" aria-hidden />}
                getOptionDescription={(option) =>
                  option.score === undefined
                    ? undefined
                    : t(`${I18N}.projects.match`, { percent: Math.round(option.score * 100) })
                }
                getOptionGroup={groupLabel}
                searchPlaceholder={t(`${I18N}.projects.search_folders`)}
                emptyMessage={t(`${I18N}.projects.no_folders`)}
                disabled={isSaving}
                contentSizing="anchor"
              >
                <Select.Trigger<TFolderOption> variant="select-lg" className="w-full">
                  {() => (
                    <span className="min-w-0 grow truncate text-left text-placeholder">
                      {t(`${I18N}.projects.choose_folder`)}
                    </span>
                  )}
                </Select.Trigger>
              </Select>
            </div>
            <Menu>
              <MenuTrigger
                render={
                  <IconButton
                    variant="secondary"
                    size="lg"
                    aria-label={t(`${I18N}.projects.more_ways`, { project: project.name })}
                    icon={<Icon icon={MoreHorizontalOutline} />}
                    loading={isSaving}
                  />
                }
              />
              <MenuContent align="end">
                <MenuItem
                  label={t(`${I18N}.projects.create`, { name: project.new_folder_name })}
                  icon={<Icon icon={FolderPlus} />}
                  onClick={create}
                />
                <MenuItem
                  label={t(`${I18N}.projects.browse`)}
                  icon={<Icon icon={FolderSearch} />}
                  onClick={() => setIsBrowsing(true)}
                />
              </MenuContent>
            </Menu>
            {isEditing && (
              <Button
                variant="ghost"
                size="sm"
                stretch="auto"
                label={t("common.cancel")}
                onClick={() => setIsEditing(false)}
              />
            )}
          </>
        )}
      </div>

      <DriveFolderBrowser
        workspaceSlug={workspaceSlug}
        within={rootFolder}
        isOpen={isBrowsing}
        onClose={() => setIsBrowsing(false)}
        onChoose={link}
      />
    </li>
  );
};
