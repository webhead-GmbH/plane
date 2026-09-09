/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { Link } from "react-router";
import { CalendarDays, Users } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Breadcrumbs, Header } from "@plane/ui";
// components
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";

export const HrHolidaysHeader = observer(function HrHolidaysHeader({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();

  return (
    <Header>
      <Header.LeftItem>
        <div className="flex items-center gap-2">
          <Breadcrumbs>
            <Breadcrumbs.Item
              component={
                <Link to={`/${workspaceSlug}/team-time`}>
                  <BreadcrumbLink label={t("hr.team_time.title")} icon={<Users className="size-4 text-tertiary" />} />
                </Link>
              }
            />
            <Breadcrumbs.Item
              component={
                <BreadcrumbLink
                  label={t("hr.holidays.title")}
                  icon={<CalendarDays className="size-4 text-tertiary" />}
                />
              }
            />
          </Breadcrumbs>
        </div>
      </Header.LeftItem>
    </Header>
  );
});
