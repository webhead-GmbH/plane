/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useSyncExternalStore } from "react";

// The container is looked up on every render: nothing announces it appearing or leaving, so there is nothing to subscribe to.
const subscribeToPortalContainer = () => () => {};

// the server has no document, so it (and the render that hydrates its HTML) has no container
const getServerPortalContainer = () => null;

/**
 * Returns the element with the given id to portal into, or null while there is none (and on the server).
 */
export const usePortalContainer = (portalId: string): HTMLElement | null => {
  const getPortalContainer = useCallback(() => document.getElementById(portalId), [portalId]);

  return useSyncExternalStore(subscribeToPortalContainer, getPortalContainer, getServerPortalContainer);
};
