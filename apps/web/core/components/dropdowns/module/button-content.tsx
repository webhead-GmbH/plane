/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { ChevronDownOutline, CloseOutline, ModuleOutline } from "@makeplane/propel/icons";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { cn } from "@plane/utils";
// hooks
import { useModule } from "@/hooks/store/use-module";
import { usePlatformOS } from "@/hooks/use-platform-os";

type ModuleButtonContentProps = {
  disabled: boolean;
  dropdownArrow: boolean;
  dropdownArrowClassName: string;
  hideIcon: boolean;
  hideText: boolean;
  onChange: (moduleIds: string[]) => void;
  placeholder?: string;
  showCount: boolean;
  showTooltip?: boolean;
  value: string | string[] | null;
  className?: string;
};

type ModuleCountLabelProps = {
  hideIcon: boolean;
  placeholder?: string;
  value: string[];
};

const ModuleCountLabel = observer(function ModuleCountLabel(props: ModuleCountLabelProps) {
  const { hideIcon, placeholder, value } = props;
  // store hooks
  const { getModuleById } = useModule();

  return (
    <div className="relative flex max-w-full items-center gap-1">
      {!hideIcon && <ModuleOutline className="h-3 w-3 flex-shrink-0" />}
      {(value.length > 0 || !!placeholder) && (
        <div className="max-w-40 truncate">
          {value.length > 0
            ? value.length === 1
              ? `${getModuleById(value[0])?.name || "module"}`
              : `${value.length} Module${value.length === 1 ? "" : "s"}`
            : placeholder}
        </div>
      )}
    </div>
  );
});

type ModuleChipListProps = {
  className?: string;
  disabled: boolean;
  hideIcon: boolean;
  hideText: boolean;
  onChange: (moduleIds: string[]) => void;
  showTooltip: boolean;
  value: string[];
};

const ModuleChipList = observer(function ModuleChipList(props: ModuleChipListProps) {
  const { className, disabled, hideIcon, hideText, onChange, showTooltip, value } = props;
  // store hooks
  const { getModuleById } = useModule();
  const { isMobile } = usePlatformOS();

  return (
    <div className="flex max-w-full flex-grow flex-wrap items-center gap-2 truncate py-0.5">
      {value.map((moduleId) => {
        const moduleDetails = getModuleById(moduleId);
        return (
          <div
            key={moduleId}
            className={cn("flex max-w-full items-center gap-1 rounded-sm bg-layer-1 py-1 text-secondary", className)}
          >
            {!hideIcon && <ModuleOutline className="h-2.5 w-2.5 flex-shrink-0" />}
            {!hideText && (
              <Tooltip
                label={`Title: ${moduleDetails?.name ?? ""}`}
                layout="stacked"
                disabled={!showTooltip || isMobile}
              >
                <span className="max-w-40 truncate text-11 font-medium">{moduleDetails?.name}</span>
              </Tooltip>
            )}
            {/* The chips sit inside the dropdown's trigger <button>, so the remove control is a pointer shortcut
                rather than a nested <button> (invalid HTML and an extra Tab stop). Its click must not reach the
                trigger, which would toggle the dropdown. Keyboard users remove a module by unticking it in the
                dropdown's options. */}
            {!disabled && (
              <Tooltip label="Remove" disabled={!showTooltip || isMobile}>
                <span className="flex-shrink-0">
                  <CloseOutline
                    className="h-2.5 w-2.5 text-tertiary hover:text-danger-primary"
                    onClick={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      const newModuleIds = value.filter((m) => m !== moduleId);
                      onChange(newModuleIds);
                    }}
                  />
                </span>
              </Tooltip>
            )}
          </div>
        );
      })}
    </div>
  );
});

export function ModuleButtonContent(props: ModuleButtonContentProps) {
  const {
    disabled,
    dropdownArrow,
    dropdownArrowClassName,
    hideIcon,
    hideText,
    onChange,
    placeholder,
    showCount,
    showTooltip = false,
    value,
    className,
  } = props;
  // store hooks
  const { getModuleById } = useModule();

  if (!Array.isArray(value))
    return (
      <>
        {!hideIcon && <ModuleOutline className="h-3 w-3 flex-shrink-0" />}
        {!hideText && (
          <span className="flex-grow truncate text-left">{value ? getModuleById(value)?.name : placeholder}</span>
        )}
        {dropdownArrow && (
          <ChevronDownOutline className={cn("h-2.5 w-2.5 flex-shrink-0", dropdownArrowClassName)} aria-hidden="true" />
        )}
      </>
    );

  return (
    <>
      {showCount ? (
        <ModuleCountLabel hideIcon={hideIcon} placeholder={placeholder} value={value} />
      ) : value.length > 0 ? (
        <ModuleChipList
          className={className}
          disabled={disabled}
          hideIcon={hideIcon}
          hideText={hideText}
          onChange={onChange}
          showTooltip={showTooltip}
          value={value}
        />
      ) : (
        <>
          {!hideIcon && <ModuleOutline className="h-3 w-3 flex-shrink-0" />}
          <span className="flex-grow truncate text-left">{placeholder}</span>
        </>
      )}
      {dropdownArrow && (
        <ChevronDownOutline className={cn("h-2.5 w-2.5 flex-shrink-0", dropdownArrowClassName)} aria-hidden="true" />
      )}
    </>
  );
}
