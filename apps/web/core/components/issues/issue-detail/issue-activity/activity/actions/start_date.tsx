/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// components
import { IssueDateActivity } from "./helpers/date-activity";

type TIssueStartDateActivity = { activityId: string; showIssue?: boolean; ends: "top" | "bottom" | undefined };

export const IssueStartDateActivity = observer(function IssueStartDateActivity(props: TIssueStartDateActivity) {
  const { activityId, showIssue = true, ends } = props;

  return <IssueDateActivity activityId={activityId} showIssue={showIssue} ends={ends} dateLabel="start date" />;
});
