/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Icon as PropelIcon } from "@makeplane/propel/components/icon";
import * as React from "react";
import { AnimatedCounter } from "./animated-counter";
import { stringToEmoji } from "../emoji-icon-picker/helper";
import { ReactionOutline } from "@makeplane/propel/icons";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { IconButton as IconButtonBox } from "@makeplane/propel/elements/icon-button";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";

export type EmojiReactionType = {
  emoji: string;
  count: number;
  reacted?: boolean;
  users?: string[];
};

export type EmojiReactionProps = React.ComponentPropsWithRef<"button"> & {
  emoji: string;
  count: number;
  reacted?: boolean;
  users?: string[];
  onReactionClick?: (emoji: string) => void;
  showCount?: boolean;
};

export type EmojiReactionGroupProps = React.ComponentPropsWithRef<"div"> & {
  reactions: EmojiReactionType[];
  onReactionClick?: (emoji: string) => void;
  showAddButton?: boolean;
  maxDisplayUsers?: number;
};

export type EmojiReactionButtonProps = React.ComponentPropsWithRef<"span">;

// one shared empty list, so a reaction without users does not hand its memo a new array each render
const NO_USERS: string[] = [];

const EmojiReaction = React.forwardRef(function EmojiReaction(
  {
    emoji,
    count,
    reacted = false,
    users = NO_USERS,
    onReactionClick,
    className,
    showCount = true,
    ...props
  }: EmojiReactionProps,
  ref: React.ForwardedRef<HTMLButtonElement>
) {
  const handleClick = () => {
    onReactionClick?.(emoji);
  };

  // propel: Tooltip's `label` is a string, so the old two-line markup is flattened
  const tooltipContent = React.useMemo(() => {
    if (!users.length) return null;

    const displayUsers = users.slice(0, 5);
    const remainingCount = users.length - displayUsers.length;

    return [
      stringToEmoji(emoji),
      `${displayUsers.join(", ")}${remainingCount > 0 ? ` and ${remainingCount} more` : ""}`,
    ].join(": ");
  }, [emoji, users]);

  const button = (
    <button
      ref={ref}
      type="button"
      onClick={handleClick}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full border px-1.5 text-caption-sm-regular transition-all duration-200",
        reacted
          ? "border-accent-strong bg-accent-primary/10 text-accent-primary"
          : "border-subtle bg-surface-1 text-tertiary hover:border-strong hover:bg-surface-2",
        className
      )}
      {...props}
    >
      <span className="leading-unset text-body-sm-regular">{emoji}</span>
      {showCount && count > 0 && (
        <AnimatedCounter count={count} size="sm" className="text-caption-sm-regular leading-normal" />
      )}
    </button>
  );

  if (tooltipContent && users.length > 0) {
    return (
      <Tooltip label={tooltipContent} layout="stacked">
        {button}
      </Tooltip>
    );
  }

  return button;
});

// This is always the content of the emoji picker's trigger button, so it is the icon button's box
// rendered as a span: a button cannot contain a button, and the trigger is what opens the picker.
// The visually hidden label is what gives that trigger button its accessible name.
const EmojiReactionButton = React.forwardRef(function EmojiReactionButton(
  { className, ...props }: EmojiReactionButtonProps,
  ref: React.ForwardedRef<HTMLSpanElement>
) {
  // plane hooks
  const { t } = useTranslation();

  return (
    <Tooltip label={t("common.actions.add_reaction")}>
      <span ref={ref} className={cn("inline-flex", className)} {...props}>
        <IconButtonBox render={<span />} variant="ghost" size="xs">
          <PropelIcon icon={<ReactionOutline className="size-3.5" />} />
        </IconButtonBox>
        <span className="sr-only">{t("common.actions.add_reaction")}</span>
      </span>
    </Tooltip>
  );
});

const EmojiReactionGroup = React.forwardRef(function EmojiReactionGroup(
  {
    reactions,
    onReactionClick,
    className,
    showAddButton = true,
    maxDisplayUsers = 5,
    ...props
  }: EmojiReactionGroupProps,
  ref: React.ForwardedRef<HTMLDivElement>
) {
  return (
    <div ref={ref} className={cn("flex flex-wrap items-center gap-2", className)} {...props}>
      {reactions.map((reaction) => (
        <EmojiReaction
          key={reaction.emoji}
          emoji={reaction.emoji}
          count={reaction.count}
          reacted={reaction.reacted}
          users={reaction.users?.slice(0, maxDisplayUsers)}
          onReactionClick={onReactionClick}
        />
      ))}
      {showAddButton && <EmojiReactionButton />}
    </div>
  );
});

EmojiReaction.displayName = "EmojiReaction";
EmojiReactionButton.displayName = "EmojiReactionButton";
EmojiReactionGroup.displayName = "EmojiReactionGroup";

export { EmojiReaction, EmojiReactionButton, EmojiReactionGroup };
