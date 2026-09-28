/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";

export type TRecharts = typeof import("recharts");

let loadedRecharts: TRecharts | null = null;
let rechartsRequest: Promise<TRecharts> | null = null;

// recharts is heavy, so it is fetched the first time a chart renders rather than with every page
// that merely links to a chart. Every chart after the first gets the module straight away.
const loadRecharts = () => {
  rechartsRequest ??= import("recharts").then((module) => {
    loadedRecharts = module;
    return module;
  });
  return rechartsRequest;
};

/** The recharts module, or null while it is still loading. */
export function useRecharts(): TRecharts | null {
  const [recharts, setRecharts] = useState<TRecharts | null>(loadedRecharts);

  useEffect(() => {
    if (recharts) return;
    let isMounted = true;
    void loadRecharts().then((module) => {
      if (isMounted) setRecharts(module);
      return module;
    });
    return () => {
      isMounted = false;
    };
  }, [recharts]);

  return recharts;
}
