/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import type { DragEvent } from "react";
// plane imports
import { CircularProgress } from "@makeplane/propel/components/circular-progress";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { CloseOutline, UploadOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import { cn, convertBytesToSize, getFileExtension } from "@plane/utils";
// components
import { getFileIcon } from "@/components/icons";
// local imports
import { stopEditorUpload, useEditorUploads } from "./editor-uploads";
import { I18N } from "./errors";

type TRowProps = {
  name: string;
  size: number;
  progress: number;
  onStop: () => void;
  className?: string;
};

/** A file on its way to Drive: how far it has got, and a way to stop it. */
export const DriveUploadRow = ({ name, size, progress, onStop, className }: TRowProps) => {
  const { t } = useTranslation();
  return (
    <div className={cn("flex items-center gap-3 text-13", className)}>
      <span className="flex shrink-0 items-center">{getFileIcon(getFileExtension(name), 18)}</span>
      <span className="min-w-0 flex-1 truncate font-medium text-secondary">{name}</span>
      <span className="shrink-0 text-placeholder">{convertBytesToSize(size)}</span>
      <CircularProgress
        value={progress}
        size="md"
        variant="brand"
        aria-label={t(`${I18N}.uploads.progress`, { name })}
      />
      <span className="w-9 shrink-0 text-right text-12 text-tertiary tabular-nums">{progress}%</span>
      <IconButton
        variant="ghost"
        size="sm"
        icon={<Icon icon={CloseOutline} />}
        aria-label={t(`${I18N}.uploads.stop`, { name })}
        onClick={(event) => {
          event.stopPropagation();
          onStop();
        }}
      />
    </div>
  );
};

/** Asks before the tab is closed or reloaded while a file is still on its way. */
export const useWarnBeforeLeaving = (active: boolean) => {
  useEffect(() => {
    if (!active) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active]);
};

/** The files an editor is sending to Drive, under the text they will appear in. */
export const DriveEditorUploads = ({
  uploadsKey,
  className,
}: {
  uploadsKey: string | undefined;
  className?: string;
}) => {
  const { t } = useTranslation();
  const rows = useEditorUploads(uploadsKey);
  useWarnBeforeLeaving(rows.length > 0);
  if (!rows.length) return null;
  return (
    <div className={cn("flex flex-col gap-1.5", className)} aria-live="polite">
      <p className="text-12 text-tertiary">{t(`${I18N}.uploads.heading`)}</p>
      {rows.map((row) => (
        <DriveUploadRow
          key={row.id}
          name={row.name}
          size={row.size}
          progress={row.progress}
          onStop={() => stopEditorUpload(row.id)}
        />
      ))}
    </div>
  );
};

const carriesFiles = (event: DragEvent) => Array.from(event.dataTransfer.types).includes("Files");

/**
 * Whether files are being dragged over an element, for showing where they can
 * be dropped. Drop is caught on the way down, since the editor inside handles
 * the drop itself and may not let it bubble back up.
 */
export const useFilesDraggedOver = (enabled: boolean) => {
  const [isOver, setIsOver] = useState(false);
  const handlers = {
    onDragEnter: (event: DragEvent) => {
      if (enabled && carriesFiles(event)) setIsOver(true);
    },
    onDragLeave: (event: DragEvent) => {
      // Moving onto a child also leaves the parent; only leaving it for outside counts.
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setIsOver(false);
    },
    onDropCapture: () => setIsOver(false),
  };
  return { isOver: enabled && isOver, handlers };
};

/** Over a box files can be dropped on, while they are dragged over it; drops pass through to what is under it. */
export const DriveDropHint = ({ show }: { show: boolean }) => {
  const { t } = useTranslation();
  if (!show) return null;
  return (
    <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-sm border-2 border-dashed border-accent-strong bg-surface-2/75">
      <span className="flex items-center gap-2 text-13 font-medium text-secondary">
        <UploadOutline className="size-4" aria-hidden />
        {t(`${I18N}.attachments.drop_here`)}
      </span>
    </div>
  );
};
