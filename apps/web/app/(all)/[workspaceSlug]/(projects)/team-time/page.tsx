/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// components
import { PageHead } from "@/components/core/page-title";
import { HrTeamMonthRoot } from "@/components/hr";

export default function TeamTimePage() {
  return (
    <>
      <PageHead title="Team time" />
      <div className="relative h-full w-full overflow-hidden overflow-y-auto">
        <HrTeamMonthRoot />
      </div>
    </>
  );
}
