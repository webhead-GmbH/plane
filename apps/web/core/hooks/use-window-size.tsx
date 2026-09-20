/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useSyncExternalStore } from "react";

// the server has no window, so it (and the render that hydrates its HTML) sees no size
const SERVER_WINDOW_SIZE = [0, 0];

let windowSize: number[] | undefined;

const subscribeToWindowSize = (onWindowSizeChange: () => void) => {
  window.addEventListener("resize", onWindowSizeChange);
  return () => {
    window.removeEventListener("resize", onWindowSizeChange);
  };
};

// hands out the same array until the window size changes, so only a real resize renders again
const getWindowSize = () => {
  const { innerWidth, innerHeight } = window;
  if (!windowSize || windowSize[0] !== innerWidth || windowSize[1] !== innerHeight) {
    windowSize = [innerWidth, innerHeight];
  }
  return windowSize;
};

const getServerWindowSize = () => SERVER_WINDOW_SIZE;

const useSize = () => useSyncExternalStore(subscribeToWindowSize, getWindowSize, getServerWindowSize);

export default useSize;
