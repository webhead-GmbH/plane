/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@makeplane/propel/components/button";
import { setToast } from "@plane/blocks/toast";
// components
import { CustomFieldsSection } from "@/components/custom-fields";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useProjectCustomFieldValues } from "@/hooks/use-project-custom-field-values";

type Props = {
  workspaceSlug: string;
  projectId: string;
  disabled?: boolean;
};

export const ProjectCustomFieldsSettings = observer(function ProjectCustomFieldsSettings(props: Props) {
  const { workspaceSlug, projectId, disabled } = props;
  // states
  const [isSaving, setIsSaving] = useState(false);
  // store hooks
  const { t } = useTranslation();
  const { updateProjectValues } = useCustomField();
  const customFields = useProjectCustomFieldValues({ workspaceSlug, projectId });

  if (!customFields.hasFields) return null;

  const handleSave = async () => {
    if (!customFields.validate()) {
      setToast({
        type: "error",
        title: t("toast.error"),
        message: t("workspace_settings.settings.custom_fields.form.required_fields_missing"),
      });
      return;
    }
    setIsSaving(true);
    try {
      await updateProjectValues(workspaceSlug, projectId, customFields.getPayload());
      setToast({
        type: "success",
        title: t("workspace_settings.settings.custom_fields.toasts.values_saved.title"),
        message: t("workspace_settings.settings.custom_fields.toasts.values_saved.message"),
      });
    } catch (_error) {
      setToast({
        type: "error",
        title: t("toast.error"),
        message: t("workspace_settings.settings.custom_fields.toasts.error.message"),
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="border-t border-subtle py-6">
      <h4 className="mb-1 text-body-md-semibold text-primary">
        {t("workspace_settings.settings.custom_fields.projects.section_title")}
      </h4>
      <p className="mb-4 text-body-sm-regular text-tertiary">
        {t("workspace_settings.settings.custom_fields.projects.section_description")}
      </p>
      <CustomFieldsSection
        fields={customFields.fields}
        values={customFields.values}
        onChange={customFields.setValue}
        errors={customFields.errors}
        disabled={disabled}
      />
      {!disabled && (
        <div className="mt-5">
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            label={t("workspace_settings.settings.custom_fields.projects.save_values")}
            onClick={handleSave}
            loading={isSaving}
          />
        </div>
      )}
    </div>
  );
});
