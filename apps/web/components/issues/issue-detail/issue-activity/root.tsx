/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useId, useMemo } from "react";
import uniq from "lodash-es/uniq";
import { observer } from "mobx-react";
// plane package imports
import type { TActivityFilters } from "@plane/constants";
import { E_SORT_ORDER, EActivityFilterType, EUserPermissions, defaultActivityFilters } from "@plane/constants";
import { useLocalStorage } from "@plane/hooks";
// i18n
import { useTranslation } from "@plane/i18n";
//types
import type { TFileSignedURLResponse, TIssueComment } from "@plane/types";
// components
import { CommentCreate } from "@/components/comments/comment-create";
import { IssueCustomFieldsTab } from "@/components/custom-fields";
import { IssueActivityWorklogCreateButton } from "@/components/issues/worklog/activity/worklog-create-button";
import { IssueWorklogList } from "@/components/issues/worklog/activity/worklog-list";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProject } from "@/hooks/store/use-project";
import { useUser, useUserPermissions } from "@/hooks/store/user";
// local imports
import { IssueActivityCommentRoot } from "./activity-comment-root";
import type { TActivityTab } from "./activity-tabs";
import { ActivityTabs, getActivityTabId, getActivityTabPanelId } from "./activity-tabs";
import { useWorkItemCommentOperations } from "./helper";
import { ActivitySortRoot } from "./sort-root";
import { ActivityFilterRoot } from "./filter-root";

type TIssueActivity = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
  isIntakeIssue?: boolean;
};

type TFeedTabKey = "all" | "activity" | "comment";
// The work item's time and its custom fields have tabs of their own, beside the feed's.
type TActivityTabKey = TFeedTabKey | "worklogs" | "custom_fields";

const DEFAULT_ACTIVITY_TAB: TActivityTabKey = "all";

/** Filters each feed tab covers; the filter menu refines within the active tab. */
const ACTIVITY_TAB_FILTERS: Record<TFeedTabKey, TActivityFilters[]> = {
  all: defaultActivityFilters,
  activity: [EActivityFilterType.ACTIVITY, EActivityFilterType.STATE, EActivityFilterType.ASSIGNEE],
  comment: [EActivityFilterType.COMMENT],
};

const ACTIVITY_TAB_KEYS: TActivityTabKey[] = ["all", "activity", "comment", "worklogs", "custom_fields"];

const isActivityTabKey = (key: string | null | undefined): key is TActivityTabKey =>
  !!key && (ACTIVITY_TAB_KEYS as string[]).includes(key);

const isFeedTab = (key: TActivityTabKey): key is TFeedTabKey =>
  Object.prototype.hasOwnProperty.call(ACTIVITY_TAB_FILTERS, key);

export type TActivityOperations = {
  createComment: (data: Partial<TIssueComment>) => Promise<TIssueComment>;
  updateComment: (commentId: string, data: Partial<TIssueComment>) => Promise<void>;
  removeComment: (commentId: string) => Promise<void>;
  uploadCommentAsset: (blockId: string, file: File, commentId?: string) => Promise<TFileSignedURLResponse>;
};

export const IssueActivity = observer(function IssueActivity(props: TIssueActivity) {
  const { workspaceSlug, projectId, issueId, disabled = false, isIntakeIssue = false } = props;
  // i18n
  const { t } = useTranslation();
  // hooks
  const { setValue: setFilterValue, storedValue: selectedFilters } = useLocalStorage(
    "issue_activity_filters",
    defaultActivityFilters
  );
  const { setValue: setSortOrder, storedValue: sortOrder } = useLocalStorage("activity_sort_order", E_SORT_ORDER.ASC);

  const { getProjectById } = useProject();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const { getProjectRoleByWorkspaceSlugAndProjectId } = useUserPermissions();
  const { data: currentUser } = useUser();
  // Time is logged by the people on the work item, or a project admin; never on an intake item.
  const issue = issueId ? getIssueById(issueId) : undefined;
  const currentUserProjectRole = getProjectRoleByWorkspaceSlugAndProjectId(workspaceSlug, projectId);
  const isAssigned = !!currentUser?.id && !!issue?.assignee_ids?.includes(currentUser.id);
  const isWorklogButtonEnabled =
    !isIntakeIssue &&
    currentUserProjectRole !== EUserPermissions.GUEST &&
    (currentUserProjectRole === EUserPermissions.ADMIN || isAssigned);

  const { setValue: setActiveTabKey, storedValue: storedActiveTabKey } = useLocalStorage<string>(
    "issue_activity_active_tab",
    DEFAULT_ACTIVITY_TAB
  );
  const tabIdPrefix = useId();

  const activityTabs: TActivityTab<TActivityTabKey>[] = [
    { key: "all", label: t("common.all") },
    { key: "activity", label: t("common.activity") },
    { key: "comment", label: t("common.comments") },
    // intake items keep no time
    ...(isIntakeIssue ? [] : [{ key: "worklogs" as const, label: t("common.worklogs") }]),
    { key: "custom_fields", label: t("common.custom_fields") },
  ];
  const storedTab = isActivityTabKey(storedActiveTabKey) ? storedActiveTabKey : DEFAULT_ACTIVITY_TAB;
  const activeTabKey: TActivityTabKey = isIntakeIssue && storedTab === "worklogs" ? DEFAULT_ACTIVITY_TAB : storedTab;
  const activeTabFilters = isFeedTab(activeTabKey) ? ACTIVITY_TAB_FILTERS[activeTabKey] : [];
  // Filters chosen in the filter menu, narrowed to the active tab. Falls back to the whole tab when
  // none of the chosen filters belong to it, so a tab never renders empty because of another tab's choice.
  const chosenTabFilters = activeTabFilters.filter((filter) =>
    (selectedFilters ?? defaultActivityFilters).includes(filter)
  );
  const effectiveFilters = chosenTabFilters.length > 0 ? chosenTabFilters : activeTabFilters;

  // toggle filter within the active tab
  const toggleFilter = (filter: TActivityFilters) => {
    const nextTabFilters = effectiveFilters.includes(filter)
      ? effectiveFilters.filter((f) => f !== filter)
      : [...effectiveFilters, filter];
    if (nextTabFilters.length === 0) return; // Ensure at least one filter is applied
    const otherFilters = (selectedFilters ?? defaultActivityFilters).filter((f) => !activeTabFilters.includes(f));
    setFilterValue(uniq([...otherFilters, ...nextTabFilters]));
  };

  const toggleSortOrder = () => {
    setSortOrder(sortOrder === E_SORT_ORDER.ASC ? E_SORT_ORDER.DESC : E_SORT_ORDER.ASC);
  };

  // helper hooks
  const activityOperations = useWorkItemCommentOperations(workspaceSlug, projectId, issueId);

  const project = getProjectById(projectId);
  const renderCommentCreationBox = useMemo(
    () => (
      <CommentCreate
        workspaceSlug={workspaceSlug}
        entityId={issueId}
        activityOperations={activityOperations}
        projectId={projectId}
      />
    ),
    [workspaceSlug, issueId, activityOperations, projectId]
  );
  if (!project) return <></>;

  const tabPanelId = getActivityTabPanelId(tabIdPrefix);
  // the comment composer belongs to the tabs that show comments
  const showCommentBox = !disabled && (activeTabKey === "all" || activeTabKey === "comment");

  return (
    <div className="py-8">
      <ActivityTabs
        tabs={activityTabs}
        activeTab={activeTabKey}
        onTabChange={(key) => setActiveTabKey(key)}
        idPrefix={tabIdPrefix}
        ariaLabel={t("common.activity")}
        actionsElement={
          <>
            {isWorklogButtonEnabled && (
              <IssueActivityWorklogCreateButton
                workspaceSlug={workspaceSlug}
                projectId={projectId}
                issueId={issueId}
                disabled={disabled}
              />
            )}
            {activeTabFilters.length > 1 && (
              <ActivityFilterRoot
                selectedFilters={effectiveFilters}
                toggleFilter={toggleFilter}
                isIntakeIssue={isIntakeIssue}
                projectId={projectId}
                filterKeys={activeTabFilters}
              />
            )}
            {isFeedTab(activeTabKey) && (
              <ActivitySortRoot sortOrder={sortOrder || E_SORT_ORDER.ASC} toggleSort={toggleSortOrder} />
            )}
          </>
        }
      />

      {/* rendering activity */}
      <div
        id={tabPanelId}
        role="tabpanel"
        aria-labelledby={getActivityTabId(tabIdPrefix, activeTabKey)}
        className="flex flex-col gap-5 py-6"
      >
        <div className="min-h-[200px]">
          {activeTabKey === "worklogs" ? (
            <IssueWorklogList workspaceSlug={workspaceSlug} projectId={projectId} issueId={issueId} />
          ) : activeTabKey === "custom_fields" ? (
            <IssueCustomFieldsTab
              workspaceSlug={workspaceSlug}
              projectId={projectId}
              issueId={issueId}
              disabled={disabled}
            />
          ) : (
            <div className="space-y-3">
              {showCommentBox && sortOrder === E_SORT_ORDER.DESC && renderCommentCreationBox}
              <IssueActivityCommentRoot
                projectId={projectId}
                workspaceSlug={workspaceSlug}
                isIntakeIssue={isIntakeIssue}
                issueId={issueId}
                selectedFilters={effectiveFilters}
                activityOperations={activityOperations}
                showAccessSpecifier={!!project.anchor}
                disabled={disabled}
                sortOrder={sortOrder || E_SORT_ORDER.ASC}
              />
              {showCommentBox && sortOrder === E_SORT_ORDER.ASC && renderCommentCreationBox}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
