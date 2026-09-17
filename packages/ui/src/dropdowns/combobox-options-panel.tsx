/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type React from "react";

type TComboboxOptionsPanelProps = React.HTMLAttributes<HTMLDivElement> & {
  panelRef: React.Ref<HTMLDivElement>;
};

/**
 * The element rendered directly inside `Combobox.Options`.
 *
 * Headless UI 2 passes the single child of `Combobox.Options` through its internal `Frozen` wrapper,
 * which clones that child with `ref: null`. A ref written on the child itself is therefore dropped and
 * react-popper never receives the panel, leaving it at `left: 0; top: 0`. Rendering the panel from
 * this component keeps the ref out of the props that get cloned.
 */
export function ComboboxOptionsPanel(props: TComboboxOptionsPanelProps) {
  const { panelRef, ...panelProps } = props;
  return <div {...panelProps} ref={panelRef} />;
}
