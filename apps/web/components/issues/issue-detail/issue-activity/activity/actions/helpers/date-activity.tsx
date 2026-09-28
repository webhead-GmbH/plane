/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { CalendarOutline } from "@makeplane/propel/icons";
// hooks
import { renderFormattedDate } from "@plane/utils";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { IssueActivityBlockComponent } from "./activity-block";
import { IssueLink } from "./issue-link";

type TIssueDateActivity = {
  activityId: string;
  showIssue: boolean;
  ends: "top" | "bottom" | undefined;
  /** The date the activity changed, as the sentence names it, e.g. "start date". */
  dateLabel: string;
};

export const IssueDateActivity = observer(function IssueDateActivity(props: TIssueDateActivity) {
  const { activityId, showIssue, ends, dateLabel } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);

  if (!activity) return <></>;
  return (
    <IssueActivityBlockComponent
      icon={<CalendarOutline width={14} height={14} className="text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>
        {activity.new_value ? `set the ${dateLabel} to ` : `removed the ${dateLabel} `}
        {activity.new_value && (
          <>
            <span className="font-medium text-primary">{renderFormattedDate(activity.new_value)}</span>
          </>
        )}
        {showIssue && (activity.new_value ? ` for ` : ` from `)}
        {showIssue && <IssueLink activityId={activityId} />}.
      </>
    </IssueActivityBlockComponent>
  );
});
