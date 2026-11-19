/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { useTranslation } from "@plane/i18n";
// services
import type { TAgentScope } from "@/services/agent-connection.service";
// local imports
import { scopeKey } from "./helpers";

/**
 * How a scope is worded for the person reading it: in their language where the web app has the
 * scope, and in the server's English otherwise, so a scope added on the server shows up
 * (untranslated) rather than as a bare id or as nothing at all.
 */
export function useScopeText() {
  const { t } = useTranslation();

  return (scope: TAgentScope) => {
    const key = scopeKey(scope.id);
    return {
      title: t(`agent.scopes.${key}.title`, { defaultValue: scope.title || scope.id }),
      description: t(`agent.scopes.${key}.description`, { defaultValue: scope.description }),
    };
  };
}
