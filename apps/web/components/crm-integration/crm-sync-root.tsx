/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { Switch } from "@makeplane/propel/components/switch";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
import { Button } from "@makeplane/propel/components/button";
import { Select } from "@plane/blocks/select";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
// services
import {
  CrmIntegrationService,
  type TCrmIntegrationPayload,
  type TCrmProjectMappingSource,
} from "@/services/crm-integration.service";

const crmIntegrationService = new CrmIntegrationService();

type Props = {
  workspaceSlug: string;
};

const I18N = "workspace_settings.settings.crm_sync";
const MAPPING_SOURCES: TCrmProjectMappingSource[] = ["custom_field", "identifier"];
// the select's values are strings, so "no field" needs one of its own
const NO_PROJECT_FIELD = "";

type TProjectFieldOption = { id: string; name: string };

export const CrmSyncRoot = observer(function CrmSyncRoot({ workspaceSlug }: Props) {
  const { t } = useTranslation();

  // form state
  const [crmApiUrl, setCrmApiUrl] = useState("");
  const [crmApiKey, setCrmApiKey] = useState("");
  const [mappingSource, setMappingSource] = useState<TCrmProjectMappingSource>("custom_field");
  const [projectIdField, setProjectIdField] = useState<string | null>(null);
  const [isActive, setIsActive] = useState(true);
  // ui state
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isBackfilling, setIsBackfilling] = useState(false);

  // data
  const {
    data: integration,
    isLoading,
    mutate,
  } = useSWR(`CRM_INTEGRATION_${workspaceSlug}`, () => crmIntegrationService.retrieve(workspaceSlug));
  const { data: projectFields } = useSWR(`CRM_PROJECT_CUSTOM_FIELDS_${workspaceSlug}`, () =>
    crmIntegrationService.fetchProjectCustomFields(workspaceSlug)
  );

  // seed the form from the saved configuration
  useEffect(() => {
    if (!integration) return;
    setCrmApiUrl(integration.crm_api_url ?? "");
    setMappingSource(integration.project_mapping_source ?? "custom_field");
    setProjectIdField(integration.crm_project_id_custom_field ?? null);
    setIsActive(integration.is_active ?? true);
  }, [integration]);

  const isConfigured = Boolean(integration?.id);
  const hasApiKey = Boolean(integration?.has_api_key);

  const buildPayload = (): TCrmIntegrationPayload => {
    const payload: TCrmIntegrationPayload = {
      crm_api_url: crmApiUrl.trim(),
      project_mapping_source: mappingSource,
      // the field is only meaningful for the custom-field mapping; clear it otherwise
      crm_project_id_custom_field: mappingSource === "custom_field" ? projectIdField || null : null,
      is_active: isActive,
    };
    // only send the key when the admin actually entered one
    if (crmApiKey.trim()) payload.crm_api_key = crmApiKey.trim();
    return payload;
  };

  const handleSave = async () => {
    if (!crmApiUrl.trim()) {
      setToast({ type: "error", title: t(`${I18N}.form.crm_url_required`) });
      return;
    }
    // a key is required the first time the integration is created
    if (!isConfigured && !crmApiKey.trim()) {
      setToast({ type: "error", title: t(`${I18N}.form.api_key_required`) });
      return;
    }
    setIsSaving(true);
    try {
      const payload = buildPayload();
      const saved = isConfigured
        ? await crmIntegrationService.update(workspaceSlug, payload)
        : await crmIntegrationService.create(workspaceSlug, payload);
      await mutate(saved, { revalidate: false });
      setCrmApiKey("");
      setToast({
        type: "success",
        title: t(`${I18N}.toasts.saved.title`),
        message: t(`${I18N}.toasts.saved.message`),
      });
    } catch {
      setToast({
        type: "error",
        title: t(`${I18N}.toasts.error.title`),
        message: t(`${I18N}.toasts.error.message`),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    try {
      const result = await crmIntegrationService.testConnection(workspaceSlug, {
        crm_api_url: crmApiUrl.trim() || undefined,
        crm_api_key: crmApiKey.trim() || undefined,
      });
      if (result.success) {
        setToast({
          type: "success",
          title: t(`${I18N}.toasts.connection_ok.title`),
          message: t(`${I18N}.toasts.connection_ok.message`, { count: result.projects_count ?? 0 }),
        });
      } else {
        throw new Error(result.error);
      }
    } catch {
      setToast({
        type: "error",
        title: t(`${I18N}.toasts.connection_failed.title`),
        message: t(`${I18N}.toasts.connection_failed.message`),
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleBackfill = async () => {
    setIsBackfilling(true);
    try {
      await crmIntegrationService.backfill(workspaceSlug);
      setToast({
        type: "success",
        title: t(`${I18N}.toasts.backfill_started.title`),
        message: t(`${I18N}.toasts.backfill_started.message`),
      });
    } catch {
      setToast({
        type: "error",
        title: t(`${I18N}.toasts.error.title`),
        message: t(`${I18N}.toasts.error.message`),
      });
    } finally {
      setIsBackfilling(false);
    }
  };

  if (isLoading && !integration) {
    return (
      <Loader className="mt-4 space-y-4">
        <Loader.Item height="40px" />
        <Loader.Item height="40px" />
        <Loader.Item height="40px" />
      </Loader>
    );
  }

  return (
    <div className="mt-4 w-full max-w-3xl space-y-6">
      {/* How syncing works */}
      <p className="text-body-sm-regular text-tertiary">{t(`${I18N}.realtime_note`)}</p>

      {/* CRM base URL */}
      <div className="flex flex-col gap-1">
        <label htmlFor="crm-url" className="text-body-sm-medium text-secondary">
          {t(`${I18N}.form.crm_url`)}
        </label>
        <InputGroup size="xl">
          <Input
            size="xl"
            id="crm-url"
            type="url"
            value={crmApiUrl}
            onChange={(e) => setCrmApiUrl(e.target.value)}
            placeholder={t(`${I18N}.form.crm_url_placeholder`)}
          />
        </InputGroup>
      </div>

      {/* API key */}
      <div className="flex flex-col gap-1">
        <label htmlFor="crm-key" className="text-body-sm-medium text-secondary">
          {t(`${I18N}.form.api_key`)}
        </label>
        <InputGroup size="xl">
          <Input
            size="xl"
            id="crm-key"
            type="password"
            autoComplete="off"
            value={crmApiKey}
            onChange={(e) => setCrmApiKey(e.target.value)}
            placeholder={hasApiKey ? t(`${I18N}.form.api_key_set`) : t(`${I18N}.form.api_key_placeholder`)}
          />
        </InputGroup>
      </div>

      {/* How each Plane project resolves to a CRM project.
          CustomSelect is a headless widget, not a native control, so the caption
          labels the group rather than dangling off a <label htmlFor>. */}
      <div className="flex flex-col gap-1" role="group" aria-labelledby="crm-mapping-source-label">
        <span id="crm-mapping-source-label" className="text-body-sm-medium text-secondary">
          {t(`${I18N}.form.mapping_source`)}
        </span>
        <Select<TCrmProjectMappingSource>
          getValues={() => MAPPING_SOURCES}
          value={mappingSource}
          onChange={(val) => setMappingSource(val as TCrmProjectMappingSource)}
          getOptionValue={(source) => source}
          getOptionLabel={(source) => t(`${I18N}.form.mapping_source_${source}`)}
          showSearch={false}
          pinSelected={false}
          contentSizing="anchor"
        >
          <Select.Trigger<TCrmProjectMappingSource> variant="select-xl" className="w-full">
            {(selected) => (
              <span className="min-w-0 grow truncate text-left">
                {t(`${I18N}.form.mapping_source_${selected[0] ?? mappingSource}`)}
              </span>
            )}
          </Select.Trigger>
        </Select>
        <p className="text-body-xs-regular text-tertiary">{t(`${I18N}.form.mapping_source_${mappingSource}_help`)}</p>
      </div>

      {/* Plane project custom field — only relevant when mapping by custom field */}
      {mappingSource === "custom_field" && (
        <div className="flex flex-col gap-1" role="group" aria-labelledby="crm-project-id-field-label">
          <span id="crm-project-id-field-label" className="text-body-sm-medium text-secondary">
            {t(`${I18N}.form.project_id_field`)}
          </span>
          <Select<TProjectFieldOption>
            getValues={() => [
              { id: NO_PROJECT_FIELD, name: t(`${I18N}.form.project_id_field_none`) },
              ...(projectFields ?? []).map((field) => ({ id: field.id, name: field.display_name })),
            ]}
            value={
              projectIdField
                ? { id: projectIdField, name: projectFields?.find((f) => f.id === projectIdField)?.display_name ?? "" }
                : null
            }
            onChange={(val) => setProjectIdField(val === NO_PROJECT_FIELD ? null : val)}
            getOptionValue={(option) => option.id}
            getOptionLabel={(option) => option.name}
            showSearch={false}
            pinSelected={false}
            contentSizing="anchor"
          >
            <Select.Trigger<TProjectFieldOption> variant="select-xl" className="w-full">
              {(selected) => (
                <span className={cn("min-w-0 grow truncate text-left", { "text-placeholder": !selected[0] })}>
                  {selected[0]?.name || t(`${I18N}.form.project_id_field_none`)}
                </span>
              )}
            </Select.Trigger>
          </Select>
          <p className="text-body-xs-regular text-tertiary">{t(`${I18N}.form.project_id_field_help`)}</p>
        </div>
      )}

      {/* Active toggle */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-body-sm-medium text-secondary">{t(`${I18N}.form.active`)}</span>
          <p className="text-body-xs-regular text-tertiary">{t(`${I18N}.form.active_help`)}</p>
        </div>
        <Switch size="sm" checked={isActive} onCheckedChange={(checked) => setIsActive(checked)} />
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-3 border-t border-subtle pt-4">
        <Button
          variant="primary"
          size="sm"
          stretch="auto"
          label={t(`${I18N}.form.save`)}
          onClick={handleSave}
          loading={isSaving}
        />
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={t(`${I18N}.form.test_connection`)}
          onClick={handleTestConnection}
          loading={isTesting}
        />
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={t(`${I18N}.form.backfill`)}
          onClick={handleBackfill}
          loading={isBackfilling}
          disabled={!isConfigured || !isActive}
        />
      </div>
    </div>
  );
});
