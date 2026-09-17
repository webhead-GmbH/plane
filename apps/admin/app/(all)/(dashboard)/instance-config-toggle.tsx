/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane internal packages
import { Switch } from "@makeplane/propel/components/switch";
import { cn } from "@plane/utils";

type Props = {
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: () => void;
  isSubmitting: boolean;
};

export function InstanceConfigToggle(props: Props) {
  const { title, description, checked, onCheckedChange, isSubmitting } = props;

  return (
    <div className={cn("flex w-full items-center gap-14 rounded-sm")}>
      <div className="flex grow items-center gap-4">
        <div className="grow">
          <div className="pb-1 text-16 font-medium">{title}</div>
          <div className={cn("text-11 leading-5 font-regular text-tertiary")}>{description}</div>
        </div>
      </div>
      <div className={`shrink-0 pr-4 ${isSubmitting && "opacity-70"}`}>
        <div className="flex items-center gap-4">
          <Switch checked={checked} onCheckedChange={onCheckedChange} size="sm" disabled={isSubmitting} />
        </div>
      </div>
    </div>
  );
}
