/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef } from "react";
import { observer } from "mobx-react";
// types
import type { IIssueDisplayProperties, TIssue } from "@plane/types";
// constants
import { SPREADSHEET_COLUMNS } from "../utils";
// components
import { useTranslation } from "@plane/i18n";
import { shouldRenderColumn } from "@/helpers/issue-filter.helper";
import { toastWorkItemUpdateFailed } from "@/components/issues/worklog/update-refusal";
import { WithDisplayPropertiesHOC } from "../properties/with-display-properties-HOC";

type Props = {
  displayProperties: IIssueDisplayProperties;
  issueDetail: TIssue;
  disableUserActions: boolean;
  property: keyof IIssueDisplayProperties;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  isEstimateEnabled: boolean;
};

export const IssueColumn = observer(function IssueColumn(props: Props) {
  const { displayProperties, issueDetail, disableUserActions, property, updateIssue } = props;
  const { t } = useTranslation();
  // router
  const tableCellRef = useRef<HTMLTableCellElement | null>(null);

  const shouldRenderProperty = shouldRenderColumn(property);

  const Column = SPREADSHEET_COLUMNS[property];

  if (!Column) return null;

  const handleUpdateIssue = async (issue: TIssue, data: Partial<TIssue>) => {
    if (!updateIssue) return;
    // Said here: the store has already put the cell back, and nothing above would.
    await updateIssue(issue.project_id, issue.id, data).catch((error) => toastWorkItemUpdateFailed(error, t));
  };

  return (
    <WithDisplayPropertiesHOC
      displayProperties={displayProperties}
      displayPropertyKey={property}
      shouldRenderProperty={() => shouldRenderProperty}
    >
      <td
        tabIndex={0}
        className="h-11 min-w-36 border-r-[0.5px] border-subtle text-body-xs-regular after:absolute after:-bottom-px after:w-full after:border-b-[0.5px] after:border-subtle nth-last-2:border-r-0"
        ref={tableCellRef}
      >
        <Column
          issue={issueDetail}
          onChange={handleUpdateIssue}
          disabled={disableUserActions}
          onClose={() => tableCellRef?.current?.focus()}
        />
      </td>
    </WithDisplayPropertiesHOC>
  );
});
