/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type React from "react";
import { useCallback, useRef } from "react";
// local imports
import { useDropdownKeyPressed } from "../hooks/use-dropdown-key-pressed";
import type { TDropdownOption } from "./dropdown";

type TUseOptionsKeyboardArgs = {
  disableSearch: boolean | undefined;
  // the options exactly as rendered, so a focused option element maps back to its option by position
  options: TDropdownOption[] | undefined;
  keyExtractor: (option: TDropdownOption) => string;
  onSelect: (value: string) => void;
  onToggle: () => void;
  onClose: () => void;
  triggerElement: HTMLButtonElement | null;
};

const getOptionElements = (list: HTMLElement) => Array.from(list.querySelectorAll<HTMLElement>('[role="option"]'));

const isEnabledOption = (element: HTMLElement) => element.getAttribute("aria-disabled") !== "true";

// the enabled option a navigation key moves focus to, or undefined when there is nowhere to go
const getNavigationTarget = (key: string, enabled: HTMLElement[], current: HTMLElement) => {
  const index = enabled.indexOf(current);
  if (key === "ArrowDown") return enabled[Math.min(index + 1, enabled.length - 1)];
  if (key === "ArrowUp") return enabled[Math.max(index - 1, 0)];
  if (key === "Home" || key === "PageUp") return enabled[0];
  if (key === "End" || key === "PageDown") return enabled[enabled.length - 1];
  return undefined;
};

/**
 * Keyboard support for the dropdown's option list.
 *
 * With a search box, Headless UI's combobox input already moves through and picks options, and the
 * keys it leaves alone close the dropdown as before. That handler cancels Enter and Escape before they
 * reach the list, so the search box closes the dropdown for those keys itself, through `closeFromSearch`.
 *
 * Without a search box there is nothing that can hold focus inside the list, so the options themselves
 * take focus: the arrow, Home and End keys move between them (Headless UI marks the focused one active),
 * Enter or Space picks it, and Escape closes the list and returns focus to the button.
 */
export const useOptionsKeyboard = (args: TUseOptionsKeyboardArgs) => {
  const { disableSearch, options, keyExtractor, onSelect, onToggle, onClose, triggerElement } = args;
  // whether the list was opened from the keyboard; read when the list mounts, never while rendering
  const openedWithKeyboardRef = useRef(false);

  // keys that reach the list from the search box
  const handleSearchKeyDown = useDropdownKeyPressed(onToggle, onClose);

  // a click the keyboard produced (Enter or Space on the button) reports no pointer presses
  const trackOpenSource = (event: React.MouseEvent<HTMLButtonElement>) => {
    openedWithKeyboardRef.current = event.detail === 0;
  };

  // move focus onto the selected (or first) option when the list opens from the keyboard without a search box
  const focusOptionOnOpen = useCallback(
    (list: HTMLUListElement | null) => {
      if (!list || !disableSearch || !openedWithKeyboardRef.current) return;
      const enabled = getOptionElements(list).filter(isEnabledOption);
      const selected = enabled.find((element) => element.getAttribute("aria-selected") === "true");
      (selected ?? enabled[0])?.focus();
    },
    [disableSearch]
  );

  const closeAndRestoreFocus = () => {
    onClose();
    triggerElement?.focus();
  };

  // called from the search box's own key handler, which runs before Headless UI's: the list closes once that
  // handler has picked the active option, so onChange still comes before onClose, and focus goes back to the
  // button once the list, with the search box that held focus, has unmounted
  const closeFromSearch = () => {
    queueMicrotask(onClose);
    requestAnimationFrame(() => triggerElement?.focus());
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLUListElement>) => {
    const optionElements = getOptionElements(event.currentTarget);
    const current = event.target as HTMLElement;
    const position = optionElements.indexOf(current);
    if (position === -1) {
      handleSearchKeyDown(event);
      return;
    }

    const target = getNavigationTarget(event.key, optionElements.filter(isEnabledOption), current);
    if (target) {
      event.preventDefault();
      target.focus();
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const option = options?.[position];
      if (option) onSelect(keyExtractor(option));
      closeAndRestoreFocus();
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeAndRestoreFocus();
    } else if (event.key === "Tab") onClose();
  };

  return { trackOpenSource, focusOptionOnOpen, handleKeyDown, closeFromSearch };
};
