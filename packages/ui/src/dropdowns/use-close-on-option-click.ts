/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useLayoutEffect, useRef } from "react";

/**
 * Closes a combobox dropdown once a click on one of its enabled options has finished.
 *
 * Headless UI's combobox picks an option on mousedown. Closing from its onChange would unmount the
 * list under the pointer and let the rest of that click land on whatever sits beneath the list, so
 * the dropdown waits for the click instead. Keyboard selection closes it from its own key handling.
 *
 * The listener sits on the panel itself rather than on the document: a list rendered from inside a
 * modal bubbles its clicks through the modal's panel in React, and Headless UI's Dialog.Panel stops
 * them there, before they could reach the document.
 */
export const useCloseOnOptionClick = (panel: HTMLElement | null, onClose: () => void, enabled: boolean) => {
  // keep the latest close handler without re-binding the listener on every render
  const onCloseRef = useRef(onClose);

  useLayoutEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    // nothing is subscribed while the list is closed, so there is nothing to clean up
    if (!enabled || !panel) return undefined;

    const handleClick = (event: MouseEvent) => {
      const option = event.target instanceof Element ? event.target.closest('[role="option"]') : null;
      if (option && option.getAttribute("aria-disabled") !== "true") onCloseRef.current();
    };

    panel.addEventListener("click", handleClick);
    return () => {
      panel.removeEventListener("click", handleClick);
    };
  }, [panel, enabled]);
};
