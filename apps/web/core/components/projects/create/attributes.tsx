/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Controller, useFormContext } from "react-hook-form";
// plane imports
import { NETWORK_CHOICES, ETabIndices } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { IProject } from "@plane/types";
import { CustomSelect } from "@plane/ui";
import { getTabIndex } from "@plane/utils";
// components
import { MemberDropdown } from "@/components/dropdowns/member/dropdown";
import { ProjectNetworkSelectOptions } from "@/components/project/network-select-options";
import { ProjectNetworkIcon } from "@/components/project/project-network-icon";

type Props = {
  isMobile?: boolean;
};

function ProjectAttributes(props: Props) {
  const { isMobile = false } = props;
  const { t } = useTranslation();
  const { control } = useFormContext<IProject>();
  const { getIndex } = getTabIndex(ETabIndices.PROJECT_CREATE, isMobile);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Controller
        name="network"
        control={control}
        render={({ field: { onChange, value } }) => {
          const currentNetwork = NETWORK_CHOICES.find((n) => n.key === value);

          return (
            <div className="h-7 flex-shrink-0" tabIndex={getIndex("network")}>
              <CustomSelect
                value={value}
                onChange={onChange}
                label={
                  <div className="flex h-full items-center gap-1">
                    {currentNetwork ? (
                      <>
                        <ProjectNetworkIcon iconKey={currentNetwork.iconKey} />
                        {t(currentNetwork.i18n_label)}
                      </>
                    ) : (
                      <span className="text-placeholder">{t("select_network")}</span>
                    )}
                  </div>
                }
                placement="bottom-start"
                className="h-full"
                buttonClassName="h-full"
                noChevron
                tabIndex={getIndex("network")}
              >
                <ProjectNetworkSelectOptions />
              </CustomSelect>
            </div>
          );
        }}
      />
      <Controller
        name="project_lead"
        control={control}
        render={({ field: { value, onChange } }) => {
          if (value === undefined || value === null || typeof value === "string")
            return (
              <div className="h-7 flex-shrink-0" tabIndex={getIndex("lead")}>
                <MemberDropdown
                  value={value ?? null}
                  onChange={(lead) => onChange(lead === value ? null : lead)}
                  placeholder={t("lead")}
                  multiple={false}
                  buttonVariant="border-with-text"
                  tabIndex={getIndex("lead")}
                />
              </div>
            );
          else return <></>;
        }}
      />
    </div>
  );
}

export default ProjectAttributes;

export { ProjectAttributes };
