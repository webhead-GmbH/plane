/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Search } from "lucide-react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
// services
import { GoogleDriveService } from "@/services/google-drive.service";
import type { TDriveProjectRow } from "@/services/google-drive.service";
// local imports
import { I18N, driveErrorMessage } from "./errors";
import { DriveProjectFolderRow } from "./project-folder-row";

const driveService = new GoogleDriveService();

/** Lower case and without accents, so "Müller" is found by typing "muller". */
const plain = (text: string) =>
  text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

const matches = (row: TDriveProjectRow, query: string) =>
  [row.project.name, row.project.identifier, row.folder?.name ?? ""].some((text) => plain(text).includes(query));

type TProps = { workspaceSlug: string; rootFolderId: string };

/**
 * Every project and the folder it keeps its files in. The folders that look
 * like a project's own are offered first, and the projects whose folder is
 * beyond doubt can all be linked at once.
 */
export const DriveProjectFoldersSection = ({ workspaceSlug, rootFolderId }: TProps) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [isLinking, setIsLinking] = useState(false);
  // Keyed by the root folder too: choosing another one changes every row's suggestions.
  const { data, error, isLoading, mutate } = useSWR(
    ["GDRIVE_PROJECTS", workspaceSlug, rootFolderId],
    () => driveService.projects(workspaceSlug),
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );
  const rows = data?.projects ?? [];
  const linkedCount = rows.filter((row) => row.folder).length;
  const clearCount = rows.filter((row) => !row.folder && row.suggestions.some((suggestion) => suggestion.clear)).length;
  const wanted = plain(query.trim());
  const shown = wanted ? rows.filter((row) => matches(row, wanted)) : rows;

  const linkClearMatches = async () => {
    setIsLinking(true);
    try {
      const { linked } = await driveService.linkSuggested(workspaceSlug);
      setToast({ type: "success", title: t(`${I18N}.projects.linked_clear`, { count: linked }) });
      await mutate();
    } catch (failure) {
      setToast({ type: "error", title: t(`${I18N}.projects.save_failed`), message: driveErrorMessage(failure, t) });
    } finally {
      setIsLinking(false);
    }
  };

  return (
    <section className="flex flex-col gap-4 border-t border-subtle pt-6" aria-labelledby="gdrive-projects-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h3 id="gdrive-projects-heading" className="text-body-md-medium text-primary">
            {t(`${I18N}.projects.heading`)}
          </h3>
          <p className="text-body-sm-regular text-tertiary">
            {data
              ? t(`${I18N}.projects.summary`, { linked: linkedCount, total: rows.length })
              : t(`${I18N}.projects.description`)}
          </p>
        </div>
        {clearCount > 0 && (
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            label={t(`${I18N}.projects.link_clear`, { count: clearCount })}
            onClick={() => void linkClearMatches()}
            loading={isLinking}
          />
        )}
      </div>

      <InputGroup size="lg">
        <Search className="ms-2.5 size-4 shrink-0 text-placeholder" aria-hidden />
        <Input
          size="lg"
          type="search"
          aria-label={t(`${I18N}.projects.search`)}
          placeholder={t(`${I18N}.projects.search`)}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </InputGroup>

      {isLoading ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="48px" />
          <Loader.Item height="48px" />
          <Loader.Item height="48px" />
        </Loader>
      ) : error ? (
        <p className="text-body-sm-regular text-danger-primary">{driveErrorMessage(error, t)}</p>
      ) : shown.length === 0 ? (
        <p className="text-body-sm-regular text-tertiary">
          {wanted ? t(`${I18N}.projects.no_results`) : t(`${I18N}.projects.no_projects`)}
        </p>
      ) : (
        <ul className="divide-y divide-subtle rounded-md border border-subtle">
          {shown.map((row) => (
            <DriveProjectFolderRow
              key={row.project.id}
              workspaceSlug={workspaceSlug}
              row={row}
              folders={data?.folders ?? []}
              onChange={() => void mutate()}
            />
          ))}
        </ul>
      )}
    </section>
  );
};
