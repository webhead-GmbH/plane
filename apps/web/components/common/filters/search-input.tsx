/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { CloseOutline, SearchOutline } from "@makeplane/propel/icons";
// hooks
import { usePlatformOS } from "@/hooks/use-platform-os";

type Props = {
  searchQuery: string;
  onSearchQueryChange: (query: string) => void;
};

export function FiltersSearchInput(props: Props) {
  const { searchQuery, onSearchQueryChange } = props;
  // hooks
  const { isMobile } = usePlatformOS();

  return (
    <div className="bg-surface-1 p-2.5 pb-0">
      <div className="flex items-center gap-1.5 rounded-sm border-[0.5px] border-subtle bg-surface-2 px-1.5 py-1 text-11">
        <SearchOutline className="text-placeholder" width={12} height={12} />
        <input
          type="text"
          className="w-full bg-surface-2 outline-none placeholder:text-placeholder"
          placeholder="Search"
          aria-label="Search filters"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          autoFocus={!isMobile}
        />
        {searchQuery !== "" && (
          <button type="button" className="grid place-items-center" onClick={() => onSearchQueryChange("")}>
            <CloseOutline className="text-tertiary" height={12} width={12} />
          </button>
        )}
      </div>
    </div>
  );
}
