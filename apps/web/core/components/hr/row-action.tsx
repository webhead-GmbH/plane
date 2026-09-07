/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Tooltip } from "@plane/ui";
import { cn } from "@plane/utils";

type TProps = {
  icon: React.ReactNode;
  /** What this does, e.g. "Approve". Shown on hover and read aloud. */
  label: string;
  /** Which row it acts on, e.g. the person or the day. */
  subject?: string;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
};

/**
 * One icon action in a table row.
 *
 * These were bare sixteen-pixel icons: nothing to aim at, no focus ring, and one
 * accessible name shared down the whole column, so a screen reader heard "Edit"
 * six times with nothing to tell the rows apart. Naming the row in the label
 * fixes that, and a 28px target is what the rest of the product gives a
 * clickable icon.
 *
 * Written as a plain button rather than a ghost `Button` because a table row
 * wants a square target with no text, and the propel Button's padding is built
 * around a label.
 */
export const HrRowAction = ({ icon, label, subject, danger, disabled, onClick }: TProps) => {
  const name = subject ? `${label} — ${subject}` : label;
  return (
    <Tooltip tooltipContent={name} position="top">
      <button
        type="button"
        aria-label={name}
        disabled={disabled}
        onClick={onClick}
        className={cn(
          "grid size-7 place-items-center rounded-md transition-colors focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none disabled:opacity-50",
          danger
            ? "text-tertiary hover:bg-layer-2 hover:text-danger-primary"
            : "text-tertiary hover:bg-layer-2 hover:text-primary"
        )}
      >
        {icon}
      </button>
    </Tooltip>
  );
};
