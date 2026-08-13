/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TIssueActivityUserDetail } from "./activity/base";

/** Enough of the work item to name and link to it, embedded by the
 *  user-active-timer endpoint so the header timer widget needs no extra fetch. */
export type TIssueWorkLogIssueDetail = {
  id: string;
  name: string;
  sequence_id: number;
  project_id: string;
  project_identifier: string;
};

export type TIssueWorkLog = {
  id: string;
  issue: string;
  project: string;
  workspace: string;
  logged_by: string;
  logged_by_detail: TIssueActivityUserDetail;
  /** Duration in seconds. null = timer is still running. */
  duration: number | null;
  started_at: string | null;
  logged_at: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  created_by?: string;
  updated_by?: string;
  /** Present only on the user-active-timer response. */
  issue_detail?: TIssueWorkLogIssueDetail;
};

export type TIssueWorkLogMap = {
  [worklog_id: string]: TIssueWorkLog;
};

export type TIssueWorkLogIdMap = {
  [issue_id: string]: string[];
};

export type TIssueWorkLogSummary = {
  total_duration: number;
  worklogs: TIssueWorkLog[];
};
