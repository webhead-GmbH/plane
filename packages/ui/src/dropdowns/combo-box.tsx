/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Combobox } from "@headlessui/react";
import type { ElementType, KeyboardEventHandler, ReactNode, Ref } from "react";
import React, { cloneElement, forwardRef, isValidElement, useEffect, useRef, useState } from "react";

type Props = {
  as?: ElementType | undefined;
  ref?: Ref<HTMLElement> | undefined;
  tabIndex?: number | undefined;
  className?: string | undefined;
  value?: string | string[] | null;
  onChange?: (value: any) => void;
  disabled?: boolean | undefined;
  onKeyDown?: KeyboardEventHandler<HTMLElement> | undefined;
  multiple?: boolean;
  renderByDefault?: boolean;
  button: ReactNode;
  children: ReactNode;
};

const ComboDropDown = forwardRef(function ComboDropDown(props: Props, ref) {
  const { button, renderByDefault = true, children, ...rest } = props;

  const dropDownButtonRef = useRef<HTMLDivElement | null>(null);

  const [shouldRender, setShouldRender] = useState(renderByDefault);

  const onHover = () => {
    setShouldRender(true);
  };

  useEffect(() => {
    const element = dropDownButtonRef.current as any;

    if (!element) return;

    element.addEventListener("mouseenter", onHover);

    return () => {
      element?.removeEventListener("mouseenter", onHover);
    };
  }, [dropDownButtonRef, shouldRender]);

  if (!shouldRender) {
    // a keyboard user never hovers, so the combobox would never mount for them: the first key on
    // the trigger mounts it and goes to the dropdown's own handler, which opens it on Enter
    const trigger = isValidElement<{ onKeyDown?: KeyboardEventHandler<HTMLElement> }>(button)
      ? cloneElement(button, {
          onKeyDown: (event: React.KeyboardEvent<HTMLElement>) => {
            button.props.onKeyDown?.(event);
            onHover();
            rest.onKeyDown?.(event);
          },
        })
      : button;

    return (
      <div ref={dropDownButtonRef} className="flex h-full items-center">
        {trigger}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-expect-error
    <Combobox {...rest} ref={ref}>
      {/* The trigger stays a plain button: Combobox.Button would force tabIndex -1 on it and swallow
          Enter, Space and ArrowDown, so keyboard users could neither reach nor open the dropdown. */}
      {button}
      {children}
    </Combobox>
  );
});

ComboDropDown.displayName = "ComboDropDown";

export { ComboDropDown };
