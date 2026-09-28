/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import type { TCycleFilters, TCycleGroups } from "@plane/types";
// components
import { FiltersSearchInput } from "@/components/common/filters/search-input";
// local imports
import { FilterEndDate } from "./end-date";
import { FilterStartDate } from "./start-date";
import { FilterStatus } from "./status";

type Props = {
  filters: TCycleFilters;
  handleFiltersUpdate: (key: keyof TCycleFilters, value: string | string[]) => void;
  isArchived?: boolean;
};

export const CycleFiltersSelection = observer(function CycleFiltersSelection(props: Props) {
  const { filters, handleFiltersUpdate, isArchived = false } = props;
  // states
  const [filtersSearchQuery, setFiltersSearchQuery] = useState("");

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <FiltersSearchInput searchQuery={filtersSearchQuery} onSearchQueryChange={setFiltersSearchQuery} />
      <div className="vertical-scrollbar scrollbar-sm h-full w-full divide-y divide-subtle-1 overflow-y-auto px-2.5">
        {/* cycle status */}
        {!isArchived && (
          <div className="py-2">
            <FilterStatus
              appliedFilters={(filters.status as TCycleGroups[]) ?? null}
              handleUpdate={(val) => handleFiltersUpdate("status", val)}
              searchQuery={filtersSearchQuery}
            />
          </div>
        )}

        {/* start date */}
        <div className="py-2">
          <FilterStartDate
            appliedFilters={filters.start_date ?? null}
            handleUpdate={(val) => handleFiltersUpdate("start_date", val)}
            searchQuery={filtersSearchQuery}
          />
        </div>

        {/* end date */}
        <div className="py-2">
          <FilterEndDate
            appliedFilters={filters.end_date ?? null}
            handleUpdate={(val) => handleFiltersUpdate("end_date", val)}
            searchQuery={filtersSearchQuery}
          />
        </div>
      </div>
    </div>
  );
});
