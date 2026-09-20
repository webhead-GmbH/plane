/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Combobox } from "@headlessui/react";
import { ChevronDownOutline, InfoOutline, SearchOutline, TickOutline } from "@makeplane/propel/icons";
import React, { useCallback, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { usePopper } from "react-popper";
import { useOutsideClickDetector } from "@plane/hooks";
// plane imports
// local imports
import { Tooltip } from "@plane/propel/tooltip";
import { useDropdownKeyDown } from "../hooks/use-dropdown-key-down";
import { cn } from "../utils";
import { ComboboxOptionsPanel } from "./combobox-options-panel";
import type { ICustomSearchSelectProps } from "./helper";
import { useCloseOnOptionClick } from "./use-close-on-option-click";

export function CustomSearchSelect(props: ICustomSearchSelectProps) {
  const {
    customButtonClassName = "",
    buttonClassName = "",
    className = "",
    chevronClassName = "",
    customButton,
    placement,
    disabled = false,
    footerOption,
    input = false,
    label,
    maxHeight = "md",
    multiple = false,
    noChevron = false,
    onChange,
    options,
    onOpen,
    onClose,
    optionsClassName = "",
    value,
    tabIndex,
    noResultsMessage = "No matches found",
    defaultOpen = false,
  } = props;
  const [query, setQuery] = useState("");

  const [referenceElement, setReferenceElement] = useState<HTMLButtonElement | null>(null);
  const [popperElement, setPopperElement] = useState<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(defaultOpen);
  // refs
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  const { styles, attributes } = usePopper(referenceElement, popperElement, {
    placement: placement ?? "bottom-start",
  });

  const filteredOptions =
    query === "" ? options : options?.filter((option) => option.query.toLowerCase().includes(query.toLowerCase()));

  // focus the search box as the panel mounts: the panel cancels the mousedown that would
  // otherwise focus it, so without this a mouse user cannot type into it
  const focusOnOpen = useCallback((el: HTMLInputElement | null) => el?.focus(), []);

  const comboboxProps: any = {
    value,
    onChange,
    disabled,
  };

  if (multiple) comboboxProps.multiple = true;

  const openDropdown = () => {
    setIsOpen(true);
    if (referenceElement) referenceElement.focus();
    if (onOpen) onOpen();
  };

  const closeDropdown = () => {
    setIsOpen(false);
    onClose && onClose();
  };

  // close from the keyboard, then hand focus back to the trigger once the panel, and the search box
  // that held focus, has unmounted
  const closeAndRestoreFocus = () => {
    closeDropdown();
    requestAnimationFrame(() => referenceElement?.focus());
  };

  // Escape from anything inside the list that is not the search box, such as a footer action
  const handleKeyDown = useDropdownKeyDown(openDropdown, closeAndRestoreFocus, isOpen);
  useOutsideClickDetector(dropdownRef, closeDropdown);

  const toggleDropdown = () => {
    if (isOpen) closeDropdown();
    else openDropdown();
  };

  // Headless UI's own handler on the search box cancels Escape and Enter, so they never reach the list;
  // this one runs before it. Enter picks the active option there and then closes a single select.
  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Escape") {
      event.stopPropagation();
      closeAndRestoreFocus();
    } else if (event.key === "Enter" && !multiple) closeAndRestoreFocus();
    else if (event.key === "Tab") closeDropdown();
  };

  // a single select closes once the click that picked an option has finished
  useCloseOnOptionClick(popperElement, closeDropdown, isOpen && !multiple);

  return (
    <Combobox
      as="div"
      ref={dropdownRef}
      className={cn("relative flex-shrink-0 text-left", className)}
      // opens Headless UI's list state as the search box takes focus, so its arrow keys and Enter work
      immediate
      {...comboboxProps}
    >
      {customButton ? (
        <button
          ref={setReferenceElement}
          type="button"
          tabIndex={tabIndex}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          disabled={disabled}
          className={cn(
            "flex w-full items-center justify-between gap-1 text-11",
            {
              "cursor-not-allowed text-secondary": disabled,
              "cursor-pointer hover:bg-layer-transparent-hover": !disabled,
            },
            customButtonClassName
          )}
          onClick={toggleDropdown}
        >
          {customButton}
        </button>
      ) : (
        <button
          ref={setReferenceElement}
          type="button"
          tabIndex={tabIndex}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          disabled={disabled}
          className={cn(
            "flex w-full items-center justify-between gap-1 rounded-sm border-[0.5px] border-strong",
            {
              "px-3 py-2 text-13": input,
              "px-2 py-1 text-11": !input,
              "cursor-not-allowed text-secondary": disabled,
              "cursor-pointer hover:bg-layer-transparent-hover": !disabled,
            },
            buttonClassName
          )}
          onClick={toggleDropdown}
        >
          {label}
          {!noChevron && !disabled && (
            <ChevronDownOutline className={cn("h-3 w-3 flex-shrink-0", chevronClassName)} aria-hidden="true" />
          )}
        </button>
      )}
      {isOpen &&
        createPortal(
          <Combobox.Options as="ul" data-prevent-outside-click static modal={false} onKeyDown={handleKeyDown}>
            <ComboboxOptionsPanel
              className={cn(
                "z-30 my-1 min-w-48 overflow-y-scroll rounded-md border-[0.5px] border-subtle-1 bg-surface-1 py-2.5 text-11 whitespace-nowrap focus:outline-none",
                optionsClassName
              )}
              panelRef={setPopperElement}
              style={styles.popper}
              {...attributes.popper}
            >
              <div className="mx-2 flex items-center gap-1.5 rounded-sm border border-subtle px-2">
                <SearchOutline className="h-3.5 w-3.5 text-placeholder" />
                <Combobox.Input
                  ref={focusOnOpen}
                  className="w-full bg-transparent py-1 text-11 text-secondary placeholder:text-placeholder focus:outline-none"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleSearchKeyDown}
                  placeholder="Search"
                  displayValue={(assigned: any) => assigned?.name}
                />
              </div>
              <div
                className={cn("vertical-scrollbar mt-2 scrollbar-xs space-y-1 overflow-y-scroll px-2", {
                  "max-h-96": maxHeight === "2xl",
                  "max-h-80": maxHeight === "xl",
                  "max-h-60": maxHeight === "lg",
                  "max-h-48": maxHeight === "md",
                  "max-h-36": maxHeight === "rg",
                  "max-h-28": maxHeight === "sm",
                })}
              >
                {filteredOptions ? (
                  filteredOptions.length > 0 ? (
                    filteredOptions.map((option) => (
                      <Combobox.Option
                        as="li"
                        key={option.value}
                        value={option.value}
                        className={({ active }) =>
                          cn(
                            "flex w-full cursor-pointer items-center justify-between gap-2 truncate rounded-sm px-1 py-1.5 select-none",
                            {
                              "bg-layer-transparent-hover": active,
                              "cursor-not-allowed text-placeholder opacity-60": option.disabled,
                            }
                          )
                        }
                        disabled={option.disabled}
                      >
                        {({ selected }) => (
                          <>
                            <span className="flex-grow truncate">{option.content}</span>
                            {selected && <TickOutline className="h-3.5 w-3.5 flex-shrink-0" />}
                            {option.tooltip && (
                              <>
                                {typeof option.tooltip === "string" ? (
                                  <Tooltip tooltipContent={option.tooltip}>
                                    <InfoOutline className="h-3.5 w-3.5 flex-shrink-0 cursor-pointer text-secondary" />
                                  </Tooltip>
                                ) : (
                                  option.tooltip
                                )}
                              </>
                            )}
                          </>
                        )}
                      </Combobox.Option>
                    ))
                  ) : (
                    <p className="px-1.5 py-1 text-placeholder italic">{noResultsMessage}</p>
                  )
                ) : (
                  <p className="px-1.5 py-1 text-placeholder italic">Loading...</p>
                )}
              </div>
              {footerOption}
            </ComboboxOptionsPanel>
          </Combobox.Options>,
          document.body
        )}
    </Combobox>
  );
}
