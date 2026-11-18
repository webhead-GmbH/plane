/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** One project's hold on an identifier, as the availability check answers it. */
export type TReservedIdentifier = {
  name: string;
  project: string;
  /** Null when the person asking may not see the project (a private one they are outside). */
  project_name: string | null;
  /** The project's identifier now: a reservation outlives a change of it. */
  project_identifier: string | null;
  project_archived: boolean | null;
};

type TTranslate = (key: string, values?: Record<string, unknown>) => string;

/**
 * Why an identifier cannot be used, naming the project that holds it. A bare "already exists" leaves a
 * person searching every project, archived ones included, for the one that has it.
 */
export function identifierTakenMessage(holder: TReservedIdentifier, t: TTranslate): string {
  if (!holder.project_name) return t("common.identifier_already_exists");
  const state = holder.project_archived ? "archived" : "active";
  // Held now, or held before and since changed: the second is the one that cannot be found by looking.
  if (holder.project_identifier === holder.name) {
    return t("common.identifier_used_by", { project: holder.project_name, state });
  }
  return t("common.identifier_reserved_by", {
    project: holder.project_name,
    current: holder.project_identifier ?? "",
    state,
  });
}
