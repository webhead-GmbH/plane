/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { MonitorOutline } from "@makeplane/propel/icons";
// components
import type { TCopyField } from "@/components/common/copy-field";
import { CopyField } from "@/components/common/copy-field";

type Props = {
  heading: string;
  commonServiceDetails: TCopyField[];
  webServiceDetails: TCopyField[];
};

export function AuthenticationProviderServiceDetails(props: Props) {
  const { heading, commonServiceDetails, webServiceDetails } = props;

  return (
    <div className="col-span-2 flex flex-col gap-y-6 md:col-span-1">
      <div className="pt-2 text-18 font-medium">{heading}</div>

      <div className="flex flex-col gap-y-4">
        {/* common service details */}
        <div className="flex flex-col gap-y-4 rounded-lg bg-layer-1 px-6 py-4">
          {commonServiceDetails.map((field) => (
            <CopyField key={field.key} label={field.label} url={field.url} description={field.description} />
          ))}
        </div>

        {/* web service details */}
        <div className="flex flex-col overflow-hidden rounded-lg">
          <div className="flex items-center gap-x-3 bg-layer-3 px-6 py-3 text-11 font-medium text-secondary uppercase">
            <MonitorOutline className="h-3 w-3" />
            Web
          </div>
          <div className="flex flex-col gap-y-4 bg-layer-1 px-6 py-4">
            {webServiceDetails.map((field) => (
              <CopyField key={field.key} label={field.label} url={field.url} description={field.description} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
