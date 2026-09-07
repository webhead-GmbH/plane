/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// components
import { useTranslation } from "@plane/i18n";
import { ContentWrapper } from "@plane/ui";
import { PageHead } from "@/components/core/page-title";
import { HrPeopleRoot } from "@/components/hr";

export default function HrPeoplePage() {
  const { t } = useTranslation();

  return (
    <>
      <PageHead title={t("hr.people.title")} />
      <ContentWrapper className="gap-7">
        <HrPeopleRoot />
      </ContentWrapper>
    </>
  );
}
