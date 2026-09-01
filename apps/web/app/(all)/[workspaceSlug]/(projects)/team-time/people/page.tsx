/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useParams } from "react-router";
// components
import { useTranslation } from "@plane/i18n";
import { PageHead } from "@/components/core/page-title";
import { HrPeopleRoot } from "@/components/hr";

export default function HrPeoplePage() {
  const { t } = useTranslation();
  const { workspaceSlug } = useParams();

  return (
    <>
      <PageHead title={t("hr.people.title")} />
      <div className="relative h-full w-full overflow-hidden overflow-y-auto">
        <HrPeopleRoot workspaceSlug={String(workspaceSlug)} />
      </div>
    </>
  );
}
