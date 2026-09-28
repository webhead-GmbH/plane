/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
// helpers
import { Button } from "@makeplane/propel/elements/button";

type Props = Omit<React.ComponentPropsWithRef<"button">, "className" | "style" | "title" | "children"> & {
  icon: React.ReactNode;
  title: string;
  disabled?: boolean;
  /**
   * Render as a span when the caller wraps this in a button of its own (the link and attachment
   * actions do): a button cannot contain a button, and the wrapper is the one that is clicked.
   */
  as?: "button" | "span";
};

/**
 * Widget toolbar button. Forwards ref and rest props to the underlying Propel `Button`, so it can be
 * used directly as a trigger's `render` element (e.g. `<MenuTrigger render={<IssueDetailWidgetButton … />} />`).
 */
export function IssueDetailWidgetButton(props: Props) {
  const { icon, title, disabled = false, as = "button", ...rest } = props;
  const content = (
    <>
      {icon}
      <span className="text-body-xs-medium">{title}</span>
    </>
  );

  if (as === "span") {
    // the chrome's own disabled look keys off aria-disabled, which a span can carry
    return (
      <Button render={<span />} variant="secondary" size="md" stretch="auto" aria-disabled={disabled || undefined}>
        {content}
      </Button>
    );
  }

  return (
    <Button {...rest} variant="secondary" disabled={disabled} size="md" stretch="auto" type="button">
      {content}
    </Button>
  );
}
