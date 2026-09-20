/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { MoreVerticalOutline } from "@makeplane/propel/icons";
import React, { forwardRef } from "react";
// helpers
import { cn } from "./utils";

interface IDragHandle {
  className?: string;
  disabled?: boolean;
  /**
   * Render the handle as a span when it sits inside another button: a button cannot contain a
   * button. The drag itself is driven by the surrounding element, so nothing else changes.
   */
  as?: "button" | "span";
}

const handleContextMenu = (e: React.MouseEvent<HTMLElement>) => {
  e.preventDefault();
  e.stopPropagation();
};

export const DragHandle = forwardRef(function DragHandle(props: IDragHandle, ref: React.ForwardedRef<HTMLElement>) {
  const { className, disabled = false, as = "button" } = props;

  if (disabled) {
    return <div className="h-[18px] w-[14px]" />;
  }

  const classNames = cn("flex flex-shrink-0 cursor-grab rounded-sm bg-surface-2 p-0.5 text-secondary", className);
  const icons = (
    <>
      <MoreVerticalOutline className="h-3.5 w-3.5 text-placeholder" />
      <MoreVerticalOutline className="-ml-5 h-3.5 w-3.5 text-placeholder" />
    </>
  );

  if (as === "span") {
    return (
      <span className={classNames} onContextMenu={handleContextMenu} ref={ref as React.ForwardedRef<HTMLSpanElement>}>
        {icons}
      </span>
    );
  }

  return (
    <button
      type="button"
      className={classNames}
      onContextMenu={handleContextMenu}
      ref={ref as React.ForwardedRef<HTMLButtonElement>}
    >
      {icons}
    </button>
  );
});

DragHandle.displayName = "DragHandle";
