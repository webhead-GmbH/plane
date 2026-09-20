/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Listbox } from "@headlessui/react";

import React, { useState } from "react";
import { createPortal } from "react-dom";
import { usePopper } from "react-popper";
import { ChevronDownOutline, TickOutline } from "@makeplane/propel/icons";
// helpers
import { cn } from "../utils";
// types
import type { ICustomSelectItemProps, ICustomSelectProps } from "./helper";

/**
 * Headless UI's Listbox.Button submits the surrounding form on Enter, and once the button has been
 * pressed with a mouse it no longer opens the list from that key. Plane's selects open on Enter, so
 * the key is handed to Headless UI as Space, which opens the list without submitting anything.
 */
const openListOnEnter = (event: React.KeyboardEvent<HTMLButtonElement>) => {
  if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
  event.preventDefault();
  event.currentTarget.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }));
};

function CustomSelect(props: ICustomSelectProps) {
  const {
    customButtonClassName = "",
    buttonClassName = "",
    placement,
    children,
    className = "",
    customButton,
    disabled = false,
    input = false,
    label,
    maxHeight = "md",
    noChevron = false,
    onChange,
    optionsClassName = "",
    value,
    tabIndex,
  } = props;
  // states
  const [referenceElement, setReferenceElement] = useState<HTMLButtonElement | null>(null);
  const [popperElement, setPopperElement] = useState<HTMLDivElement | null>(null);

  const { styles, attributes } = usePopper(referenceElement, popperElement, {
    placement: placement ?? "bottom-start",
  });

  // Listbox owns the open state: its button opens the list from the mouse or the keyboard, the list
  // takes focus for arrow keys, type-ahead, Enter and Escape, and choosing an option closes it.
  return (
    <Listbox
      as="div"
      value={value}
      onChange={onChange}
      className={cn("relative flex-shrink-0 text-left", className)}
      disabled={disabled}
    >
      {({ open }) => (
        <>
          {customButton ? (
            <Listbox.Button as={React.Fragment}>
              <button
                ref={setReferenceElement}
                type="button"
                tabIndex={tabIndex}
                className={`flex items-center justify-between gap-1 rounded text-11 ${
                  disabled ? "cursor-not-allowed text-secondary" : "cursor-pointer hover:bg-layer-transparent-hover"
                } ${customButtonClassName}`}
                onKeyDown={openListOnEnter}
              >
                {customButton}
              </button>
            </Listbox.Button>
          ) : (
            <Listbox.Button as={React.Fragment}>
              <button
                ref={setReferenceElement}
                type="button"
                tabIndex={tabIndex}
                className={cn(
                  "flex w-full items-center justify-between gap-1 rounded border border-strong",
                  {
                    "px-3 py-2 text-13": input,
                    "px-2 py-1 text-11": !input,
                    "cursor-not-allowed text-secondary": disabled,
                    "cursor-pointer hover:bg-layer-transparent-hover": !disabled,
                  },
                  buttonClassName
                )}
                onKeyDown={openListOnEnter}
              >
                {label}
                {!noChevron && !disabled && <ChevronDownOutline className="h-3 w-3" aria-hidden="true" />}
              </button>
            </Listbox.Button>
          )}
          {open &&
            createPortal(
              <Listbox.Options as="ul" className="focus:outline-none" data-prevent-outside-click>
                <div
                  className={cn(
                    "z-30 my-1 min-w-48 overflow-y-scroll rounded-md border-[0.5px] border-subtle-1 bg-surface-1 px-2 py-2.5 text-11 whitespace-nowrap focus:outline-none",
                    optionsClassName
                  )}
                  ref={setPopperElement}
                  style={styles.popper}
                  {...attributes.popper}
                >
                  <div
                    className={cn("space-y-1 overflow-y-scroll", {
                      "max-h-60": maxHeight === "lg",
                      "max-h-48": maxHeight === "md",
                      "max-h-36": maxHeight === "rg",
                      "max-h-28": maxHeight === "sm",
                    })}
                  >
                    {children}
                  </div>
                </div>
              </Listbox.Options>,
              document.body
            )}
        </>
      )}
    </Listbox>
  );
}

function Option(props: ICustomSelectItemProps) {
  const { children, value, className } = props;

  return (
    <Listbox.Option
      as="li"
      value={value}
      className={({ active }) =>
        cn(
          "flex cursor-pointer items-center justify-between gap-2 truncate rounded-sm px-1 py-1.5 text-secondary select-none",
          {
            "bg-layer-transparent-hover": active,
          },
          className
        )
      }
    >
      {({ selected }) => (
        <div className="flex w-full items-center justify-between gap-2">
          {children}
          {selected && <TickOutline className="h-3.5 w-3.5 flex-shrink-0" />}
        </div>
      )}
    </Listbox.Option>
  );
}

CustomSelect.Option = Option;

export { CustomSelect };
