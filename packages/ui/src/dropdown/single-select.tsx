/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Combobox } from "@headlessui/react";
import { sortBy } from "lodash-es";
import React, { useMemo, useRef, useState } from "react";
import { usePopper } from "react-popper";
// plane imports
import { useOutsideClickDetector } from "@plane/hooks";
// local imports
import { ComboboxOptionsPanel } from "../dropdowns/combobox-options-panel";
import { useCloseOnOptionClick } from "../dropdowns/use-close-on-option-click";
import { cn } from "../utils";
import { DropdownButton } from "./common";
import { DropdownOptions } from "./common/options";
import type { ISingleSelectDropdown } from "./dropdown";
import { useOptionsKeyboard } from "./use-options-keyboard";

export function Dropdown(props: ISingleSelectDropdown) {
  const {
    value,
    onChange,
    options,
    onOpen,
    onClose,
    containerClassName,
    tabIndex,
    placement,
    disabled,
    buttonContent,
    buttonContainerClassName,
    buttonClassName,
    disableSearch,
    inputPlaceholder,
    inputClassName,
    inputIcon,
    inputContainerClassName,
    keyExtractor,
    optionsContainerClassName,
    queryArray,
    sortByKey,
    firstItem,
    renderItem,
    loader = false,
    disableSorting,
  } = props;

  // states
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [popperElement, setPopperElement] = useState<HTMLDivElement | null>(null);
  // refs
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  // popper-js refs
  const [referenceElement, setReferenceElement] = useState<HTMLButtonElement | null>(null);

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

  // handlers
  const toggleDropdown = () => {
    if (!isOpen) onOpen?.();
    setIsOpen((prevIsOpen) => !prevIsOpen);
    if (isOpen) onClose?.();
  };

  const handleClose = () => {
    if (!isOpen) return;
    setIsOpen(false);
    onClose?.();
    setQuery?.("");
  };

  // options
  const sortedOptions = useMemo(() => {
    if (!options) return undefined;

    const filteredOptions = queryArray
      ? (options || []).filter((options) => {
          const queryString = queryArray.map((query) => options.data[query]).join(" ");
          return queryString.toLowerCase().includes(query.toLowerCase());
        })
      : options;

    if (disableSorting || !sortByKey) return filteredOptions;

    return sortBy(filteredOptions, [
      (option) => firstItem && firstItem(option.data[option.value]),
      (option) => !(value ?? []).includes(option.data[option.value]),
      () => sortByKey && sortByKey.toLowerCase(),
    ]);
  }, [query, options]);

  // hooks
  const { trackOpenSource, focusOptionOnOpen, handleKeyDown, closeFromSearch } = useOptionsKeyboard({
    disableSearch,
    options: sortedOptions,
    keyExtractor,
    onSelect: onChange,
    onToggle: toggleDropdown,
    onClose: handleClose,
    triggerElement: referenceElement,
  });

  useOutsideClickDetector(dropdownRef, handleClose, true);

  const handleOnClick = (e: React.MouseEvent<HTMLButtonElement, MouseEvent>) => {
    e.stopPropagation();
    e.preventDefault();
    trackOpenSource(e);
    toggleDropdown();
  };

  // close once the click that picked an option has finished
  useCloseOnOptionClick(popperElement, handleClose, isOpen);

  return (
    <Combobox
      as="div"
      ref={dropdownRef}
      value={value}
      // Headless UI v2 widens a non-multiple Combobox to `T | null`. v1 never emitted
      // null, so drop it here and keep this component's non-nullable onChange contract.
      onChange={(selected) => {
        if (selected !== null) onChange(selected);
      }}
      className={cn(
        "h-full",
        typeof containerClassName === "function" ? containerClassName(isOpen) : containerClassName
      )}
      disabled={disabled}
      // opens Headless UI's list state as the search box takes focus, so its arrow keys and Enter work
      immediate
    >
      <DropdownButton
        value={value}
        isOpen={isOpen}
        setReferenceElement={setReferenceElement}
        handleOnClick={handleOnClick}
        buttonContent={buttonContent}
        buttonClassName={buttonClassName}
        buttonContainerClassName={buttonContainerClassName}
        disabled={disabled}
        tabIndex={tabIndex}
      />
      {isOpen && (
        // not modal: the search box sits inside the list, and Headless UI's modal mode makes everything
        // beside the focused box inert, the options included
        <Combobox.Options
          as="ul"
          className="fixed z-10"
          static
          modal={false}
          ref={focusOptionOnOpen}
          onKeyDown={handleKeyDown}
        >
          <ComboboxOptionsPanel
            className={cn(
              "my-1 w-48 rounded-sm border-[0.5px] border-strong bg-surface-1 px-2 py-2 text-11 shadow-raised-200 focus:outline-none",
              optionsContainerClassName
            )}
            panelRef={setPopperElement}
            style={styles.popper}
            {...attributes.popper}
          >
            <DropdownOptions
              isOpen={isOpen}
              query={query}
              setQuery={setQuery}
              inputIcon={inputIcon}
              inputPlaceholder={inputPlaceholder}
              inputClassName={inputClassName}
              inputContainerClassName={inputContainerClassName}
              disableSearch={disableSearch}
              keyExtractor={keyExtractor}
              options={sortedOptions}
              value={value}
              renderItem={renderItem}
              loader={loader}
              handleClose={closeFromSearch}
            />
          </ComboboxOptionsPanel>
        </Combobox.Options>
      )}
    </Combobox>
  );
}
