/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type React from "react";
import { useEffect, useLayoutEffect, useRef } from "react";

export const useOutsideClickDetector = (
  ref: React.RefObject<HTMLElement | null> | any,
  callback: () => void,
  useCapture = false,
  enabled = true
) => {
  // Keep the latest callback in a ref so the document listener binds once per consumer
  // instead of re-attaching on every render. useCapture is an effect dependency, so the
  // listener is re-bound with the new phase whenever it changes.
  const callbackRef = useRef(callback);

  useLayoutEffect(() => {
    callbackRef.current = callback;
  });

  useEffect(() => {
    // nothing is subscribed while disabled, so there is nothing to clean up
    if (!enabled) return undefined;

    const handleClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as any)) {
        // check for the closest element with attribute name data-prevent-outside-click
        const preventOutsideClickElement = (event.target as unknown as HTMLElement | undefined)?.closest(
          "[data-prevent-outside-click]"
        );
        // if the closest element with attribute name data-prevent-outside-click is found, return
        if (preventOutsideClickElement) {
          return;
        }
        // else call the callback
        callbackRef.current();
      }
    };

    document.addEventListener("mousedown", handleClick, useCapture);
    return () => {
      document.removeEventListener("mousedown", handleClick, useCapture);
    };
  }, [ref, enabled, useCapture]);
};
