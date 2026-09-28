/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { ECustomFieldEntityType, TCustomField } from "@plane/types";
import { Dialog, DialogContent } from "@makeplane/propel/components/dialog";
import { setToast } from "@plane/blocks/toast";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
// local imports
import { FieldForm } from "./field-form";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
  entityType: ECustomFieldEntityType;
  data?: TCustomField | null;
};

export const CreateUpdateFieldModal = observer(function CreateUpdateFieldModal(props: Props) {
  const { isOpen, onClose, workspaceSlug, entityType, data } = props;
  // states
  const [isSubmitting, setIsSubmitting] = useState(false);
  // store hooks
  const { createCustomField, updateCustomField, getCustomFieldsByEntity } = useCustomField();
  const { t } = useTranslation();

  const handleSubmit = async (payload: Partial<TCustomField>) => {
    setIsSubmitting(true);
    try {
      if (data?.id) {
        await updateCustomField(workspaceSlug, entityType, data.id, payload);
        setToast({
          type: "success",
          title: t("workspace_settings.settings.custom_fields.toasts.updated.title"),
          message: t("workspace_settings.settings.custom_fields.toasts.updated.message"),
        });
      } else {
        // place the new field at the end
        const existing = getCustomFieldsByEntity(entityType) ?? [];
        const nextSortOrder = existing.reduce((max, field) => Math.max(max, field.sort_order), 0) + 100;
        await createCustomField(workspaceSlug, entityType, {
          ...payload,
          sort_order: nextSortOrder,
        });
        setToast({
          type: "success",
          title: t("workspace_settings.settings.custom_fields.toasts.created.title"),
          message: t("workspace_settings.settings.custom_fields.toasts.created.message"),
        });
      }
      onClose();
    } catch (error) {
      const message =
        (error as { settings?: string; error?: string })?.settings ??
        (error as { error?: string })?.error ??
        t("workspace_settings.settings.custom_fields.toasts.error.message");
      setToast({
        type: "error",
        title: t("workspace_settings.settings.custom_fields.toasts.error.title"),
        message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="md">
        <FieldForm
          key={data?.id ?? "new"}
          data={data}
          isSubmitting={isSubmitting}
          onSubmit={handleSubmit}
          handleClose={onClose}
        />
      </DialogContent>
    </Dialog>
  );
});
