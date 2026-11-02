/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Link, useParams } from "react-router";
import { User, Users } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Breadcrumbs } from "@plane/blocks/breadcrumb";
import { Header } from "@plane/blocks/layout";
// components
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
// services
import { HrService } from "@/services/hr.service";

const hrService = new HrService();

export function HrPersonMonthHeader({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const { profileId } = useParams();
  const { data: people } = useSWR("HR_EMPLOYEES", () => hrService.employees());
  const name = people?.find((person) => person.id === profileId)?.member_display_name ?? "";

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
            {name ? (
              <Breadcrumbs.Item
                component={<BreadcrumbLink label={name} icon={<User className="size-4 text-tertiary" />} />}
              />
            ) : null}
          </Breadcrumbs>
        </div>
      </Header.LeftItem>
    </Header>
  );
}
