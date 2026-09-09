/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Card, ECardDirection, ECardSpacing } from "@plane/ui";
import { cn } from "@plane/utils";

type TProps = {
  label: string;
  value: string;
  hint?: string;
  tone?: string;
  /** Panel treatment where this figure is the one that needs acting on. */
  accent?: string;
};

/**
 * A headline figure, on the product's own card.
 *
 * The same `Card` in the same configuration the personal work summary uses for
 * its stat tiles — column, small spacing — so the ground, the hairline, the
 * corner, the padding and the hover lift are not merely matched but are the
 * same code. Hand-copying those measurements is how a module drifts a shade at a
 * time until it reads as something bolted on, and this one had already been
 * copied twice before it was shared.
 *
 * `accent` marks the figure that is the point of the screen. A tinted panel
 * behind it rather than a louder number, so a set of them stays legible.
 */
export const HrFigure = ({ label, value, hint, tone, accent }: TProps) => (
  <Card direction={ECardDirection.COLUMN} spacing={ECardSpacing.SM} className={cn("gap-1 space-y-0", accent)}>
    <span className="text-13 text-placeholder">{label}</span>
    <span className={cn("text-18 font-semibold tabular-nums", tone ?? "text-primary")}>{value}</span>
    {hint ? <span className="text-11 text-tertiary">{hint}</span> : null}
  </Card>
);
