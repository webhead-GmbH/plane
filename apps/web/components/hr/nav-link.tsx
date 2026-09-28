/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Link } from "react-router";

type TProps = {
  to: string;
  icon: React.ReactNode;
  children: React.ReactNode;
};

/**
 * A link to another part of the module.
 *
 * Deliberately lighter than a button. These sat in a row of six identical
 * secondary buttons alongside the exports, so somewhere to go and something to
 * do carried the same weight and the reader had to sort out which was which.
 * A quiet link that fills in on hover reads as navigation on sight.
 */
export const HrNavLink = ({ to, icon, children }: TProps) => (
  <Link
    to={to}
    className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-13 text-secondary transition-colors hover:bg-layer-2 hover:text-primary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
  >
    <span className="text-tertiary">{icon}</span>
    {children}
  </Link>
);
