/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useRef, useState } from "react";
import { observer } from "mobx-react";
import { usePopper } from "react-popper";
// plane imports
import { useTranslation } from "@plane/i18n";
import { StateGroupIcon } from "@plane/propel/icons";
import { ChevronDownOutline } from "@makeplane/propel/icons";
import type { IState } from "@plane/types";
import { ComboDropDown, Spinner } from "@plane/ui";
import { cn } from "@plane/utils";
// components
import { DropdownButton } from "@/components/dropdowns/buttons";
import { BUTTON_VARIANTS_WITH_TEXT } from "@/components/dropdowns/constants";
import type { TButtonVariants, TDropdownProps } from "@/components/dropdowns/types";
// hooks
import { useDropdown } from "@/hooks/use-dropdown";
// local imports
import { StateDropdownOptions } from "./state-options";

export type TWorkItemStateDropdownBaseProps = TDropdownProps & {
  alwaysAllowStateChange?: boolean;
  button?: ReactNode;
  dropdownArrow?: boolean;
  dropdownArrowClassName?: string;
  filterAvailableStateIds?: boolean;
  getStateById: (stateId: string | null | undefined) => IState | undefined;
  iconSize?: string;
  isForWorkItemCreation?: boolean;
  isInitializing?: boolean;
  onChange: (val: string) => void;
  onClose?: () => void;
  onDropdownOpen?: () => void;
  projectId: string | undefined;
  renderByDefault?: boolean;
  showDefaultState?: boolean;
  stateIds: string[];
  value: string | undefined | null;
};

type TWorkItemStateButtonContentProps = {
  buttonVariant: TButtonVariants;
  dropdownArrow: boolean;
  dropdownArrowClassName: string;
  hideIcon: boolean;
  iconSize: string;
  isInitializing: boolean;
  selectedState: IState | undefined;
};

const WorkItemStateButtonContent = observer(function WorkItemStateButtonContent(
  props: TWorkItemStateButtonContentProps
) {
  const { buttonVariant, dropdownArrow, dropdownArrowClassName, hideIcon, iconSize, isInitializing, selectedState } =
    props;
  // plane hooks
  const { t } = useTranslation();

  if (isInitializing) return <Spinner className="h-3.5 w-3.5" />;

  return (
    <>
      {!hideIcon && (
        <StateGroupIcon
          stateGroup={selectedState?.group ?? "backlog"}
          color={selectedState?.color ?? "var(--text-color-tertiary)"}
          className={cn("flex-shrink-0", iconSize)}
          percentage={selectedState?.order}
        />
      )}
      {BUTTON_VARIANTS_WITH_TEXT.includes(buttonVariant) && (
        <span className="flex-grow truncate text-left">{selectedState?.name ?? t("state")}</span>
      )}
      {dropdownArrow && (
        <ChevronDownOutline className={cn("h-2.5 w-2.5 flex-shrink-0", dropdownArrowClassName)} aria-hidden="true" />
      )}
    </>
  );
});

export const WorkItemStateDropdownBase = observer(function WorkItemStateDropdownBase(
  props: TWorkItemStateDropdownBaseProps
) {
  const {
    button,
    buttonClassName,
    buttonContainerClassName,
    buttonVariant,
    className = "",
    disabled = false,
    dropdownArrow = false,
    dropdownArrowClassName = "",
    getStateById,
    hideIcon = false,
    iconSize = "size-4",
    isInitializing = false,
    onChange,
    onClose,
    onDropdownOpen,
    placement,
    renderByDefault = true,
    showDefaultState = true,
    showTooltip = false,
    stateIds,
    tabIndex,
    value,
  } = props;
  // refs
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  // popper-js refs
  const [referenceElement, setReferenceElement] = useState<HTMLButtonElement | null>(null);
  const [popperElement, setPopperElement] = useState<HTMLDivElement | null>(null);
  // states
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  // store hooks
  const { t } = useTranslation();
  const statesList = stateIds.map((stateId) => getStateById(stateId)).filter((state) => !!state);
  const defaultState = statesList?.find((state) => state?.default);
  const stateValue = value ? value : showDefaultState ? defaultState?.id : undefined;
  // popper-js init
  const { styles, attributes } = usePopper(referenceElement, popperElement, {
    placement: placement ?? "bottom-start",
    modifiers: [
      {
        name: "preventOverflow",
        options: {
          padding: 12,
        },
      },
    ],
  });
  // dropdown init
  const { handleClose, handleKeyDown, handleOnClick, searchInputKeyDown } = useDropdown({
    dropdownRef,
    inputRef,
    isOpen,
    onClose,
    onOpen: onDropdownOpen,
    query,
    setIsOpen,
    setQuery,
  });

  // derived values
  const options = statesList?.map((state) => ({
    value: state?.id,
    query: `${state?.name}`,
    content: (
      <div className="flex items-center gap-2">
        <StateGroupIcon
          stateGroup={state?.group ?? "backlog"}
          color={state?.color}
          className={cn("flex-shrink-0", iconSize)}
          percentage={state?.order}
        />
        <span className="flex-grow truncate text-left">{state?.name}</span>
      </div>
    ),
  }));

  const filteredOptions =
    query === "" ? options : options?.filter((o) => o.query.toLowerCase().includes(query.toLowerCase()));

  const selectedState = stateValue ? getStateById(stateValue) : undefined;

  const dropdownOnChange = (val: string) => {
    onChange(val);
    handleClose();
  };

  const comboButton = button ? (
    <button
      ref={setReferenceElement}
      type="button"
      className={cn("clickable block h-full w-full outline-none", buttonContainerClassName)}
      onClick={handleOnClick}
      disabled={disabled}
      tabIndex={tabIndex}
      aria-haspopup="listbox"
      aria-expanded={isOpen}
    >
      {button}
    </button>
  ) : (
    <button
      tabIndex={tabIndex}
      ref={setReferenceElement}
      type="button"
      className={cn(
        "clickable block h-full max-w-full outline-none",
        {
          "cursor-not-allowed text-secondary": disabled,
          "cursor-pointer": !disabled,
        },
        buttonContainerClassName
      )}
      onClick={handleOnClick}
      disabled={disabled}
      aria-haspopup="listbox"
      aria-expanded={isOpen}
    >
      <DropdownButton
        className={buttonClassName}
        isActive={isOpen}
        tooltipHeading={t("state")}
        tooltipContent={selectedState?.name ?? t("state")}
        showTooltip={showTooltip}
        variant={buttonVariant}
        renderToolTipByDefault={renderByDefault}
      >
        <WorkItemStateButtonContent
          buttonVariant={buttonVariant}
          dropdownArrow={dropdownArrow}
          dropdownArrowClassName={dropdownArrowClassName}
          hideIcon={hideIcon}
          iconSize={iconSize}
          isInitializing={isInitializing}
          selectedState={selectedState}
        />
      </DropdownButton>
    </button>
  );

  return (
    // oxlint-disable-next-line jsx_a11y/no-static-element-interactions
    <ComboDropDown
      as="div"
      ref={dropdownRef}
      className={cn("h-full", className)}
      value={stateValue}
      onChange={dropdownOnChange}
      disabled={disabled}
      onKeyDown={handleKeyDown}
      button={comboButton}
      renderByDefault={renderByDefault}
    >
      {isOpen && (
        <StateDropdownOptions
          filteredOptions={filteredOptions}
          inputRef={inputRef}
          popperAttributes={attributes.popper}
          popperStyle={styles.popper}
          query={query}
          searchInputKeyDown={searchInputKeyDown}
          setPopperElement={setPopperElement}
          setQuery={setQuery}
          stateOptionProps={props}
          value={value}
        />
      )}
    </ComboDropDown>
  );
});
