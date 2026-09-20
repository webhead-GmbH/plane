/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import type { TModuleStatus } from "@plane/propel/icons";
// plane imports
import type { TModuleDisplayFilters, TModuleFilters } from "@plane/types";
// components
import { FiltersSearchInput } from "@/components/common/filters/search-input";
import { FilterOption } from "@/components/issues/issue-layouts/filters";
import { FilterLead, FilterMembers, FilterStartDate, FilterStatus, FilterTargetDate } from "@/components/modules";

type Props = {
  displayFilters: TModuleDisplayFilters;
  filters: TModuleFilters;
  handleDisplayFiltersUpdate: (updatedDisplayProperties: Partial<TModuleDisplayFilters>) => void;
  handleFiltersUpdate: (key: keyof TModuleFilters, value: string | string[]) => void;
  memberIds?: string[] | undefined;
  isArchived?: boolean;
};

export const ModuleFiltersSelection = observer(function ModuleFiltersSelection(props: Props) {
  const {
    displayFilters,
    filters,
    handleDisplayFiltersUpdate,
    handleFiltersUpdate,
    memberIds,
    isArchived = false,
  } = props;
  // states
  const [filtersSearchQuery, setFiltersSearchQuery] = useState("");

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <FiltersSearchInput searchQuery={filtersSearchQuery} onSearchQueryChange={setFiltersSearchQuery} />
      <div className="vertical-scrollbar scrollbar-sm h-full w-full divide-y divide-subtle-1 overflow-y-auto px-2.5">
        {!isArchived && (
          <div className="py-2">
            <FilterOption
              isChecked={!!displayFilters.favorites}
              onClick={() =>
                handleDisplayFiltersUpdate({
                  favorites: !displayFilters.favorites,
                })
              }
              title="Favorites"
            />
          </div>
        )}

        {/* status */}
        {!isArchived && (
          <div className="py-2">
            <FilterStatus
              appliedFilters={(filters.status as TModuleStatus[]) ?? null}
              handleUpdate={(val) => handleFiltersUpdate("status", val)}
              searchQuery={filtersSearchQuery}
            />
          </div>
        )}

        {/* lead */}
        <div className="py-2">
          <FilterLead
            appliedFilters={filters.lead ?? null}
            handleUpdate={(val) => handleFiltersUpdate("lead", val)}
            searchQuery={filtersSearchQuery}
            memberIds={memberIds}
          />
        </div>

        {/* members */}
        <div className="py-2">
          <FilterMembers
            appliedFilters={filters.members ?? null}
            handleUpdate={(val) => handleFiltersUpdate("members", val)}
            searchQuery={filtersSearchQuery}
            memberIds={memberIds}
          />
        </div>

        {/* start date */}
        <div className="py-2">
          <FilterStartDate
            appliedFilters={filters.start_date ?? null}
            handleUpdate={(val) => handleFiltersUpdate("start_date", val)}
            searchQuery={filtersSearchQuery}
          />
        </div>

        {/* target date */}
        <div className="py-2">
          <FilterTargetDate
            appliedFilters={filters.target_date ?? null}
            handleUpdate={(val) => handleFiltersUpdate("target_date", val)}
            searchQuery={filtersSearchQuery}
          />
        </div>
      </div>
    </div>
  );
});
