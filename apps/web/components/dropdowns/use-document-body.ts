/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useSyncExternalStore } from "react";

// the body element never changes, so there is nothing to subscribe to
const subscribeToDocumentBody = () => () => {};
const getDocumentBody = () => document.body;
// the server has no document, so it (and the render that hydrates its HTML) has no body to portal into
const getServerDocumentBody = () => null;

/**
 * @description the document body that dropdown options are portalled into: null on the server and for the render
 * that hydrates its HTML, document.body from the render after that and for every component mounted later
 */
export const useDocumentBody = (): HTMLElement | null =>
  useSyncExternalStore(subscribeToDocumentBody, getDocumentBody, getServerDocumentBody);
