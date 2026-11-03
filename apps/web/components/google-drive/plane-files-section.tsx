/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { convertBytesToSize } from "@plane/utils";
// services
import { GoogleDriveService } from "@/services/google-drive.service";
// local imports
import { I18N, driveErrorMessage } from "./errors";

const driveService = new GoogleDriveService();

type TProps = { workspaceSlug: string };

/**
 * Attachments that were added before their project had a folder, still on the
 * Plane server, and moving them all to Drive at once to free its space. Shown
 * only while there are some.
 */
export const DrivePlaneFilesSection = ({ workspaceSlug }: TProps) => {
  const { t } = useTranslation();
  const [isStarting, setIsStarting] = useState(false);
  // Asked again every few seconds while they move, so the count goes down as they go.
  const { data, mutate } = useSWR(["GDRIVE_PLANE_FILES", workspaceSlug], () => driveService.planeFiles(workspaceSlug), {
    shouldRetryOnError: false,
    refreshInterval: (latest) => (latest?.moving ? 3000 : 0),
  });

  if (!data || (data.count === 0 && !data.moving)) return null;

  const moveAll = async () => {
    setIsStarting(true);
    try {
      await driveService.moveAllPlaneFiles(workspaceSlug);
      await mutate();
    } catch (failure) {
      setToast({ type: "error", title: t(`${I18N}.plane_files.failed`), message: driveErrorMessage(failure, t) });
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <section className="flex flex-col gap-3 border-t border-subtle pt-6" aria-labelledby="gdrive-plane-files-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h3 id="gdrive-plane-files-heading" className="text-body-md-medium text-primary">
            {t(`${I18N}.plane_files.heading`)}
          </h3>
          <p className="text-body-sm-regular text-tertiary" aria-live="polite">
            {data.moving
              ? t(`${I18N}.plane_files.moving`, { count: data.count })
              : t(`${I18N}.plane_files.description`, { count: data.count, size: convertBytesToSize(data.size) })}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={t(`${I18N}.plane_files.move`)}
          loading={isStarting || data.moving}
          disabled={data.moving}
          onClick={() => void moveAll()}
        />
      </div>
    </section>
  );
};
