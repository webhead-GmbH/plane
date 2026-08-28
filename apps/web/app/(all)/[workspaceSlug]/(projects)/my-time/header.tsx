/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { Clock } from "lucide-react";
// plane imports
import { Breadcrumbs, Header } from "@plane/ui";
// components
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";

export const MyTimeHeader = observer(function MyTimeHeader() {
  return (
    <Header>
      <Header.LeftItem>
        <div className="flex items-center gap-2">
          <Breadcrumbs>
            <Breadcrumbs.Item
              component={<BreadcrumbLink label="My time" icon={<Clock className="size-4 text-tertiary" />} />}
            />
          </Breadcrumbs>
        </div>
      </Header.LeftItem>
    </Header>
  );
});
