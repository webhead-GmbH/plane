/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// components
import { PageHead } from "@/components/core/page-title";
import { MyTimeRoot } from "@/components/hr";

export default function MyTimePage() {
  return (
    <>
      <PageHead title="My time" />
      <div className="relative h-full w-full overflow-hidden overflow-y-auto">
        <MyTimeRoot />
      </div>
    </>
  );
}
