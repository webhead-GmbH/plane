/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactElement } from "react";
import { useTranslation } from "@plane/i18n";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import {
  Menu,
  MenuContent,
  MenuItem,
  MenuSubmenu,
  MenuSubmenuContent,
  MenuSubmenuTrigger,
  MenuTrigger,
} from "@makeplane/propel/components/menu";
import { MoreHorizontalOutline } from "@makeplane/propel/icons";
import { toSideAndAlign } from "@plane/blocks/common";
import type { TContextMenuItem } from "@plane/blocks/context-menu";
import { getRenderableItems, resolveItemVariant } from "@plane/blocks/context-menu";
import { quickActionTriggerGuard, isNativeQuickActionTrigger, stopQuickActionPropagation } from "./helper";

type TQuickActionMenuContentProps = {
  items: TContextMenuItem[];
  placements: Parameters<typeof toSideAndAlign>[0];
};

// The items of a work item's quick-action menu, with one level of submenus. Every quick-action
// dropdown renders the same list, only the items differ.
export function QuickActionMenuContent(props: TQuickActionMenuContentProps) {
  const { items, placements } = props;

  return (
    <MenuContent {...toSideAndAlign(placements)} onClick={stopQuickActionPropagation}>
      {getRenderableItems(items).map((item) => {
        const nestedItems = getRenderableItems(item.nestedMenuItems);
        if (nestedItems.length > 0) {
          return (
            <MenuSubmenu key={item.key}>
              <MenuSubmenuTrigger
                variant={resolveItemVariant(item)}
                icon={item.icon ? <Icon icon={item.icon} /> : undefined}
                label={item.title ?? ""}
                disabled={item.disabled}
              />
              <MenuSubmenuContent sizing="auto">
                {nestedItems.map((nestedItem) => (
                  <MenuItem
                    key={nestedItem.key}
                    variant={resolveItemVariant(nestedItem)}
                    icon={nestedItem.icon ? <Icon icon={nestedItem.icon} /> : undefined}
                    label={nestedItem.title ?? ""}
                    description={nestedItem.description}
                    onClick={() => {
                      nestedItem.action();
                    }}
                    disabled={nestedItem.disabled}
                  />
                ))}
              </MenuSubmenuContent>
            </MenuSubmenu>
          );
        }
        return (
          <MenuItem
            key={item.key}
            variant={resolveItemVariant(item)}
            icon={item.icon ? <Icon icon={item.icon} /> : undefined}
            label={item.title ?? ""}
            description={item.description}
            onClick={() => {
              item.action();
            }}
            disabled={item.disabled}
          />
        );
      })}
    </MenuContent>
  );
}

type TQuickActionMenuProps = TQuickActionMenuContentProps & {
  customActionButton?: ReactElement;
};

// A quick-action menu opened by the caller's own trigger, or by an icon-only fallback.
export function QuickActionMenu(props: TQuickActionMenuProps) {
  const { items, placements, customActionButton } = props;
  const { t } = useTranslation();

  return (
    <Menu>
      <MenuTrigger
        {...quickActionTriggerGuard}
        nativeButton={isNativeQuickActionTrigger(customActionButton)}
        aria-label={t("aria_labels.common.more_actions")}
        render={
          customActionButton ?? (
            // Icon-only fallback trigger, so it needs an explicit accessible name.
            <IconButton
              variant="ghost"
              size="sm"
              aria-label={t("aria_labels.common.more_actions")}
              icon={<Icon icon={MoreHorizontalOutline} />}
            />
          )
        }
      />
      <QuickActionMenuContent items={items} placements={placements} />
    </Menu>
  );
}
