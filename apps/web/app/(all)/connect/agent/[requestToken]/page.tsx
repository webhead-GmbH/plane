/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// components
import { AgentConsentRoot } from "@/components/agent/consent/root";
// lib
import { AuthenticationWrapper } from "@/lib/wrappers/authentication-wrapper";
// local imports
import type { Route } from "./+types/page";

/**
 * Where a person lands from the link an app gave them, to say yes or no to connecting it.
 *
 * Signing in is the wrapper's job: somebody who is not signed in is sent to the sign-in page with this
 * page's address as `next_path`, and comes back here once they are.
 */
export default function ConnectAgentPage({ params }: Route.ComponentProps) {
  return (
    <AuthenticationWrapper>
      <AgentConsentRoot requestToken={params.requestToken} />
    </AuthenticationWrapper>
  );
}
