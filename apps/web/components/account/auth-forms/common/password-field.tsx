/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
// icons
import { HideOutline, ShowOutline } from "@makeplane/propel/icons";
// plane imports
import { Input, InputGroup } from "@makeplane/propel/components/input";

type Props = {
  id: string;
  label: string;
  value: string | undefined;
  placeholder: string;
  isPasswordVisible: boolean;
  onTogglePasswordVisibility: () => void;
  onChange: (value: string) => void;
  onFocus: () => void;
  onBlur: () => void;
  minLength?: number;
  autoFocus?: boolean;
  children?: ReactNode;
};

export function AuthPasswordField(props: Props) {
  const {
    id,
    label,
    value,
    placeholder,
    isPasswordVisible,
    onTogglePasswordVisibility,
    onChange,
    onFocus,
    onBlur,
    minLength,
    autoFocus,
    children,
  } = props;

  return (
    <div className="space-y-1">
      <label className="text-13 font-medium text-tertiary" htmlFor={id}>
        {label}
      </label>
      <InputGroup size="2xl">
        <Input
          size="2xl"
          type={isPasswordVisible ? "text" : "password"}
          name={id}
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          minLength={minLength}
          onFocus={onFocus}
          onBlur={onBlur}
          autoComplete="new-password"
          autoFocus={autoFocus}
        />
        <button type="button" onClick={onTogglePasswordVisibility} className="grid size-5 place-items-center">
          {isPasswordVisible ? (
            <HideOutline className="size-5 text-placeholder" />
          ) : (
            <ShowOutline className="size-5 text-placeholder" />
          )}
        </button>
      </InputGroup>
      {children}
    </div>
  );
}
