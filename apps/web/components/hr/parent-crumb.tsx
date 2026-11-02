/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Link } from "react-router";
import { Clock, Users } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// components
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
// local imports
import { useHrAccess } from "./hr-manager-only";

/**
 * The way back from a page that employees reach as well as whoever runs HR.
 * Team time refuses employees, so for them the way back is their own month.
 */
export function HrParentCrumb({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const { data } = useHrAccess();

  if (data && !data.is_hr_manager)
    return (
      <Link to={`/${workspaceSlug}/my-time`}>
        <BreadcrumbLink label={t("hr.my_time.title")} icon={<Clock className="size-4 text-tertiary" />} />
      </Link>
    );

  return (
    <Link to={`/${workspaceSlug}/team-time`}>
      <BreadcrumbLink label={t("hr.team_time.title")} icon={<Users className="size-4 text-tertiary" />} />
    </Link>
  );
}
