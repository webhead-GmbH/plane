/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// ui
import { Button } from "@makeplane/propel/components/button";
import type { IExportData } from "@plane/types";
// helpers
import { getDate, renderFormattedDate } from "@plane/utils";
// types

type Props = {
  service: IExportData;
  refreshing: boolean;
};

const PROVIDER_LABELS: Record<string, string> = { csv: "CSV", xlsx: "Excel", json: "JSON" };

const STATUS_CLASSNAMES: Record<string, string> = {
  completed: "bg-success-subtle text-success-primary",
  processing: "bg-yellow-500/20 text-yellow-500",
  failed: "bg-danger-subtle text-danger-primary",
  expired: "bg-orange-500/20 text-orange-500",
};

export function SingleExport({ service, refreshing }: Props) {
  const provider = service.provider;

  const [isLoading] = useState(false);
  const downloadLabel = isLoading ? "Downloading..." : "Download";

  const checkExpiry = (inputDateString: string) => {
    const currentDate = new Date();
    const expiryDate = getDate(inputDateString);
    if (!expiryDate) return false;
    expiryDate.setDate(expiryDate.getDate() + 7);
    return expiryDate > currentDate;
  };

  return (
    <div className="flex items-center justify-between gap-2 px-4 py-3">
      <div>
        <h4 className="flex items-center gap-2 text-13">
          <span>
            Export to <span className="font-medium">{PROVIDER_LABELS[provider] ?? ""}</span>{" "}
          </span>
          <span className={`rounded-sm px-2 py-0.5 text-11 capitalize ${STATUS_CLASSNAMES[service.status] ?? ""}`}>
            {refreshing ? "Refreshing..." : service.status}
          </span>
        </h4>
        <div className="mt-2 flex items-center gap-2 text-11 text-secondary">
          <span>{renderFormattedDate(service.created_at)}</span>|
          <span>Exported by {service?.initiated_by_detail?.display_name}</span>
        </div>
      </div>
      {checkExpiry(service.created_at) ? (
        <>
          {service.status == "completed" && (
            <div>
              <Button
                variant="primary"
                size="sm"
                stretch="full"
                label={downloadLabel}
                nativeButton={false}
                render={
                  <a target="_blank" href={service?.url} rel="noopener noreferrer">
                    {downloadLabel}
                  </a>
                }
              />
            </div>
          )}
        </>
      ) : (
        <div className="text-11 text-danger-primary">Expired</div>
      )}
    </div>
  );
}
