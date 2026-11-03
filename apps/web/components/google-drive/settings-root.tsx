/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { useSearchParams } from "react-router";
import useSWR from "swr";
// plane imports
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
// services
import { GoogleDriveService } from "@/services/google-drive.service";
import type { TDriveConnection } from "@/services/google-drive.service";
// local imports
import { DriveConnectionSection } from "./connection-section";
import { I18N, driveErrorMessage } from "./errors";
import { DriveProjectFoldersSection } from "./project-folders-section";
import { DriveRootFolderSection } from "./root-folder-section";

const driveService = new GoogleDriveService();

// What Google's sign-in came back with, as the callback puts it in the address.
const OUTCOMES = new Set(["connected", "refused", "failed", "no_refresh_token"]);

type TProps = { workspaceSlug: string };

/**
 * Google Drive for the workspace, in the order it is set up: connect, say
 * where the project folders are, then give each project its folder.
 */
export const GoogleDriveSettingsRoot = ({ workspaceSlug }: TProps) => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const outcome = searchParams.get("drive");
  const {
    data: connection,
    error,
    isLoading,
    mutate,
  } = useSWR(["GDRIVE_CONNECTION", workspaceSlug], () => driveService.connection(workspaceSlug), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  // Said once, then taken out of the address so a reload does not say it again.
  useEffect(() => {
    if (!outcome || !OUTCOMES.has(outcome)) return;
    setToast({
      type: outcome === "connected" ? "success" : "error",
      title: t(`${I18N}.outcome.${outcome}.title`),
      message: t(`${I18N}.outcome.${outcome}.message`),
    });
    setSearchParams(
      (params) => {
        params.delete("drive");
        return params;
      },
      { replace: true }
    );
  }, [outcome, setSearchParams, t]);

  const update = (next: TDriveConnection) => void mutate(next, { revalidate: false });

  if (isLoading) {
    return (
      <Loader className="mt-4 space-y-4">
        <Loader.Item height="40px" />
        <Loader.Item height="40px" />
        <Loader.Item height="120px" />
      </Loader>
    );
  }
  if (error || !connection) {
    return <p className="mt-4 text-body-sm-regular text-danger-primary">{driveErrorMessage(error, t)}</p>;
  }

  return (
    <div className="mt-4 flex w-full max-w-4xl flex-col gap-6">
      <DriveConnectionSection workspaceSlug={workspaceSlug} connection={connection} onChange={update} />
      {connection.connected && (
        <DriveRootFolderSection workspaceSlug={workspaceSlug} connection={connection} onChange={update} />
      )}
      {connection.connected && connection.root_folder && (
        <DriveProjectFoldersSection workspaceSlug={workspaceSlug} rootFolderId={connection.root_folder.id} />
      )}
    </div>
  );
};
