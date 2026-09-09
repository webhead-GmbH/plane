/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Outlet, useParams } from "react-router";
import { AppHeader } from "@/components/core/app-header";
import { ContentWrapper } from "@/components/core/content-wrapper";
import { HrAbsencesHeader } from "./header";

export default function HrAbsencesLayout() {
  const { workspaceSlug } = useParams();

  return (
    <>
      <AppHeader header={<HrAbsencesHeader workspaceSlug={String(workspaceSlug)} />} />
      <ContentWrapper>
        <Outlet />
      </ContentWrapper>
    </>
  );
}
