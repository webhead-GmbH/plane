/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";

import { useTranslation } from "@plane/i18n";
import { DeleteOutline, MoreHorizontalOutline } from "@makeplane/propel/icons";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import type { TIssueServiceType } from "@plane/types";
import { EIssueServiceType } from "@plane/types";
// ui
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { convertBytesToSize, getFileExtension, getFileName, getFileURL, renderFormattedDate } from "@plane/utils";
// components
//
import { ButtonAvatars } from "@/components/dropdowns/member/avatar";
import { getFileIcon } from "@/components/icons";
// helpers
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useMember } from "@/hooks/store/use-member";
import { usePlatformOS } from "@/hooks/use-platform-os";

type TIssueAttachmentsListItem = {
  attachmentId: string;
  disabled?: boolean;
  issueServiceType?: TIssueServiceType;
};

export const IssueAttachmentsListItem = observer(function IssueAttachmentsListItem(props: TIssueAttachmentsListItem) {
  const { t } = useTranslation();
  // props
  const { attachmentId, disabled, issueServiceType = EIssueServiceType.ISSUES } = props;
  // store hooks
  const { getUserDetails } = useMember();
  const {
    attachment: { getAttachmentById },
    toggleDeleteAttachmentModal,
  } = useIssueDetail(issueServiceType);
  // derived values
  const attachment = attachmentId ? getAttachmentById(attachmentId) : undefined;
  const fileName = getFileName(attachment?.attributes.name ?? "");
  const fileExtension = getFileExtension(attachment?.attributes.name ?? "");
  const fileIcon = getFileIcon(fileExtension, 18);
  const fileURL = getFileURL(attachment?.asset_url ?? "");
  // hooks
  const { isMobile } = usePlatformOS();

  if (!attachment) return <></>;

  return (
    <div className="group flex h-11 items-center hover:bg-surface-2">
      {/* Opening the attachment is this button's job alone. The row itself is not one: it also
          holds the actions menu, and a button cannot contain another. Between them the two
          halves cover the whole row, and neither lets a click through to the drop zone
          around the list, which would open the file picker. */}
      <button
        type="button"
        className="flex h-full min-w-0 flex-1 items-center gap-3 truncate pl-3 text-left text-13"
        onClick={(e) => {
          e.stopPropagation();
          window.open(fileURL, "_blank", "noopener,noreferrer");
        }}
      >
        <span className="flex items-center gap-3">{fileIcon}</span>
        <Tooltip label={`${fileName}.${fileExtension}`} layout="stacked" disabled={isMobile}>
          <span className="truncate font-medium text-secondary">{`${fileName}.${fileExtension}`}</span>
        </Tooltip>
        <span className="flex size-1.5 shrink-0 rounded-full bg-layer-1" />
        <span className="shrink-0 text-placeholder">{convertBytesToSize(attachment.attributes.size)}</span>
      </button>

      <div role="presentation" className="flex h-full items-center gap-3 px-3" onClick={(e) => e.stopPropagation()}>
        {attachment?.created_by && (
          <Tooltip
            label={`${
              getUserDetails(attachment?.created_by)?.display_name ?? ""
            } uploaded on ${renderFormattedDate(attachment.updated_at)}`}
            layout="stacked"
            disabled={isMobile}
          >
            <div className="flex items-center justify-center">
              <ButtonAvatars showTooltip userIds={attachment?.created_by} />
            </div>
          </Tooltip>
        )}

        <Menu>
          {/* Icon-only trigger, so it needs an explicit accessible name. */}
          <MenuTrigger
            render={
              <IconButton
                variant="ghost"
                size="sm"
                disabled={disabled}
                aria-label={t("aria_labels.common.more_actions")}
                icon={<Icon icon={MoreHorizontalOutline} />}
              />
            }
          />
          <MenuContent side="bottom" align="end">
            <MenuItem
              icon={<Icon icon={DeleteOutline} />}
              label={t("common.actions.delete")}
              onClick={() => {
                toggleDeleteAttachmentModal(attachmentId);
              }}
            />
          </MenuContent>
        </Menu>
      </div>
    </div>
  );
});
