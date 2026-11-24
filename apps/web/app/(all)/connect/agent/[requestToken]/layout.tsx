/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Outlet } from "react-router";
import type { Route } from "./+types/layout";

// The address of this page carries a one-time link for connecting an app. Nothing in it should reach
// another site: not in a Referer header, not in a search index. Repeated here rather than inherited,
// because a route's meta replaces its parent's.
export const meta: Route.MetaFunction = () => [
  { title: "Connect an app" },
  { name: "referrer", content: "no-referrer" },
  { name: "robots", content: "noindex, nofollow" },
  { name: "viewport", content: "width=device-width, initial-scale=1, minimum-scale=1, viewport-fit=cover" },
];

export default function ConnectAgentLayout() {
  return <Outlet />;
}
