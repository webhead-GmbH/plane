/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import * as React from "react";
import { useRef, useState } from "react";
import { Tooltip } from "@plane/propel/tooltip";
import type { ICustomSearchSelectOption } from "@plane/types";
import { CustomSearchSelect } from "../dropdowns";
import { cn } from "../utils";
import { Breadcrumbs } from "./breadcrumbs";

type TBreadcrumbNavigationSearchDropdownProps = {
  icon?: React.ReactNode;
  title?: string;
  selectedItem: string;
  navigationItems: ICustomSearchSelectOption[];
  onChange?: (value: string) => void;
  navigationDisabled?: boolean;
  isLast?: boolean;
  handleOnClick?: () => void;
  disableRootHover?: boolean;
  shouldTruncate?: boolean;
};

export function BreadcrumbNavigationSearchDropdown(props: TBreadcrumbNavigationSearchDropdownProps) {
  const {
    icon,
    title,
    selectedItem,
    navigationItems,
    onChange,
    navigationDisabled = false,
    isLast = false,
    handleOnClick,
    shouldTruncate = false,
  } = props;
  // state
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  // refs
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  // The title is its own button beside the dropdown's trigger, not inside it: a button cannot contain
  // a button, and as part of the trigger the title could not be reached or used with a keyboard.
  // The last crumb has nowhere to navigate to, so there its click opens the dropdown, as it always has.
  const handleTitleClick = () => {
    if (!isLast) {
      handleOnClick?.();
      return;
    }
    dropdownRef.current?.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]')?.click();
  };

  return (
    <div
      className={cn("group flex h-full items-center gap-0.5 rounded-sm hover:bg-surface-2", {
        "bg-surface-2": isDropdownOpen,
      })}
    >
      <Tooltip tooltipContent={title} position="bottom">
        <button
          type="button"
          onClick={handleTitleClick}
          disabled={navigationDisabled && isLast}
          className={cn(
            "group flex h-full cursor-pointer items-center gap-2 rounded-sm rounded-r-none px-1.5 py-1 text-13 font-medium text-tertiary outline-none",
            {
              "hover:bg-layer-1 hover:text-primary": !isLast,
            }
          )}
        >
          {shouldTruncate && <div className="flex text-tertiary @4xl:hidden">...</div>}
          <div
            className={cn("flex gap-2", {
              "hidden items-center gap-2 @4xl:flex": shouldTruncate,
            })}
          >
            {icon && <Breadcrumbs.Icon>{icon}</Breadcrumbs.Icon>}
            <Breadcrumbs.Label>{title}</Breadcrumbs.Label>
          </div>
        </button>
      </Tooltip>
      <div ref={dropdownRef} className="h-full">
        <CustomSearchSelect
          onOpen={() => {
            setIsDropdownOpen(true);
          }}
          onClose={() => {
            setIsDropdownOpen(false);
          }}
          options={navigationItems}
          value={selectedItem}
          onChange={(value: string) => {
            if (value !== selectedItem) {
              onChange?.(value);
            }
          }}
          customButton={
            <Breadcrumbs.Separator
              className={cn("rounded-r-sm", {
                "bg-layer-1": isDropdownOpen && !isLast,
                "hover:bg-layer-1": !isLast,
              })}
              containerClassName="p-0"
              iconClassName={cn("group-hover:rotate-90 hover:text-primary", {
                "text-primary": isDropdownOpen,
                "rotate-90": isDropdownOpen || isLast,
              })}
              showDivider={!isLast}
            />
          }
          disabled={navigationDisabled}
          className="h-full rounded-sm"
          customButtonClassName="flex h-full cursor-pointer items-center rounded-sm outline-none"
        />
      </div>
    </div>
  );
}
