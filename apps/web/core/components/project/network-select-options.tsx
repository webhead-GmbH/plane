/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { NETWORK_CHOICES } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { CustomSelect } from "@plane/ui";
// local imports
import { ProjectNetworkIcon } from "./project-network-icon";

/** The options of a project network select: each network with its icon, name and what it means. */
export function ProjectNetworkSelectOptions() {
  const { t } = useTranslation();

  return (
    <>
      {NETWORK_CHOICES.map((network) => (
        <CustomSelect.Option key={network.key} value={network.key}>
          <div className="flex items-start gap-2">
            <ProjectNetworkIcon iconKey={network.iconKey} className="h-3.5 w-3.5" />
            <div className="-mt-1">
              <p>{t(network.i18n_label)}</p>
              <p className="text-11 text-placeholder">{t(network.description)}</p>
            </div>
          </div>
        </CustomSelect.Option>
      ))}
    </>
  );
}
