/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import type { ReactNode } from "react";
// plane imports
import { ConfirmDialog } from "@plane/blocks/dialog";
import { useTranslation } from "@plane/i18n";
// services
import { CrmIntegrationService } from "@/services/crm-integration.service";
import type { TIdentifierChangeImpact } from "@/services/crm-integration.service";

const crmService = new CrmIntegrationService();

type TTranslate = (key: string, values?: Record<string, unknown>) => string;

/**
 * What to tell somebody before a changed Project ID is saved, one line each, or none when it touches nothing
 * outside Plane. With the CRM mapped by identifier the Project ID is the CRM project number, so a change moves
 * the project's CRM tasks (and their timers and hours) to another CRM project; and the Drive folders carry
 * it in their names.
 */
export function identifierChangeLines(impact: TIdentifierChangeImpact, identifier: string, t: TTranslate): string[] {
  const lines: string[] = [];
  const { crm, drive } = impact;

  if (crm) {
    // A bare number does not say whose project it is; the name is what shows a wrong one.
    const project = crm.target === null ? "" : crm.target_name ? `${crm.target} (${crm.target_name})` : `${crm.target}`;
    if (crm.target === null) lines.push(t("common.identifier_change_crm_stops", { identifier }));
    else if (crm.tasks > 0) lines.push(t("common.identifier_change_crm_moves", { count: crm.tasks, project }));
    else if (crm.current === null) lines.push(t("common.identifier_change_crm_starts", { project }));
  }

  if (drive) {
    if (drive.folder) {
      lines.push(t("common.identifier_change_drive_folder", { from: drive.folder.from, to: drive.folder.to }));
    }
    if (drive.work_items > 0) lines.push(t("common.identifier_change_drive_items", { count: drive.work_items }));
    if (drive.folder || drive.work_items > 0) lines.push(t("common.identifier_change_drive_stay"));
  }

  return lines;
}

type TPending = { lines: string[]; answer: (confirmed: boolean) => void };

/**
 * Asks before a Project ID change that reaches outside Plane is saved.
 *
 * `confirm` resolves to whether to go on: at once when the change touches nothing outside Plane, or when the
 * check itself could not be made (saving must not depend on the CRM being reachable), and otherwise once the
 * person has answered the dialog. Render `dialog` anywhere in the form.
 */
export function useProjectIdentifierChange(workspaceSlug: string, projectId: string) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<TPending | null>(null);

  const confirm = async (identifier: string): Promise<boolean> => {
    let lines: string[];
    try {
      lines = identifierChangeLines(
        await crmService.identifierChangeImpact(workspaceSlug, projectId, identifier),
        identifier,
        t
      );
    } catch {
      return true;
    }
    if (lines.length === 0) return true;
    return new Promise<boolean>((answer) => setPending({ lines, answer }));
  };

  const settle = (confirmed: boolean) => {
    pending?.answer(confirmed);
    setPending(null);
  };

  const dialog: ReactNode = (
    <ConfirmDialog
      isOpen={pending !== null}
      handleClose={() => settle(false)}
      handleSubmit={() => settle(true)}
      isSubmitting={false}
      variant="warning"
      title={t("common.identifier_change_title")}
      // The dialog puts its content in a paragraph, so the lines are spans: a list cannot sit in one.
      content={
        <span className="flex flex-col gap-2">
          {pending?.lines.map((line) => (
            <span key={line} className="flex gap-2">
              <span aria-hidden>•</span>
              <span>{line}</span>
            </span>
          ))}
        </span>
      }
      primaryButtonText={{ default: t("common.identifier_change_confirm") }}
      secondaryButtonText={t("common.cancel")}
    />
  );

  return { confirmIdentifierChange: confirm, identifierChangeDialog: dialog };
}
