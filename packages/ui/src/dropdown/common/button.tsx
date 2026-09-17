/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
// helper
import { cn } from "../../utils";
import type { IMultiSelectDropdownButton, ISingleSelectDropdownButton } from "../dropdown";

export function DropdownButton(props: IMultiSelectDropdownButton | ISingleSelectDropdownButton) {
  const {
    isOpen,
    buttonContent,
    buttonClassName,
    buttonContainerClassName,
    handleOnClick,
    value,
    setReferenceElement,
    disabled,
    tabIndex,
  } = props;
  return (
    // a plain button: Combobox.Button would force tabIndex -1 on it and swallow Enter and Space, so keyboard
    // users could neither reach nor open the dropdown
    <button
      ref={setReferenceElement}
      type="button"
      tabIndex={tabIndex}
      aria-haspopup="listbox"
      aria-expanded={isOpen}
      disabled={disabled}
      className={cn(
        "clickable block h-full max-w-full outline-none",
        {
          "cursor-not-allowed text-secondary": disabled,
          "cursor-pointer": !disabled,
        },
        buttonContainerClassName
      )}
      onClick={handleOnClick}
    >
      {buttonContent ? <>{buttonContent(isOpen, value)}</> : <span className={cn("", buttonClassName)}>{value}</span>}
    </button>
  );
}
