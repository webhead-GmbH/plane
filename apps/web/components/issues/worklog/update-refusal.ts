/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { setToast } from "@plane/blocks/toast";

type TTranslate = (key: string, values?: Record<string, unknown>) => string;

/**
 * What to say when a change to a work item is refused.
 *
 * The server names the one refusal people can act on — a timer still running on
 * the work item keeps it out of states where time is not tracked — so that one is
 * said in the reader's language. Anything else gets the general sentence.
 */
export function workItemUpdateFailedMessage(failure: unknown, t: TTranslate): string {
  const reason = failure && typeof failure === "object" ? (failure as { reason?: unknown }).reason : undefined;
  if (reason === "timer_running") return t("common.stop_timer_first");
  return t("entity.update.failed", { entity: t("issue.label", { count: 1 }) });
}

/** The error toast for a refused change to a work item. */
export function toastWorkItemUpdateFailed(failure: unknown, t: TTranslate): void {
  setToast({ type: "error", title: t("common.error.label"), message: workItemUpdateFailedMessage(failure, t) });
}
