/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { MutableRefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import { dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { autoScrollForElements } from "@atlaskit/pragmatic-drag-and-drop-auto-scroll/element";
import { observer } from "mobx-react";
// plane constants
import { DRAG_ALLOWED_GROUPS } from "@plane/constants";
// i18n
import { useTranslation } from "@plane/i18n";
//types
import { setToast } from "@plane/blocks/toast";
import type {
  TGroupedIssues,
  TIssue,
  IIssueDisplayProperties,
  IIssueMap,
  TSubGroupedIssues,
  TIssueGroupByOptions,
  TIssueOrderByOptions,
} from "@plane/types";
import { EIssueLayoutTypes } from "@plane/types";
import { cn } from "@plane/utils";
import type { GroupDropLocation } from "@/components/issues/issue-layouts/utils";
// components
import {
  highlightIssueOnDrop,
  getSourceFromDropPayload,
  getDestinationFromDropPayload,
  getIssueBlockId,
} from "@/components/issues/issue-layouts/utils";
import { KanbanIssueBlockLoader } from "@/components/ui/loader/layouts/kanban-layout-loader";
import { useWorkFlowFDragNDrop } from "@/components/workflow";
// hooks
import { useProjectState } from "@/hooks/store/use-project-state";
import { useIntersectionObserver } from "@/hooks/use-intersection-observer";
import { useIssuesStore } from "@/hooks/use-issue-layout-store";
// local imports
import { GroupDragOverlay } from "../group-drag-overlay";
import type { TRenderQuickActions } from "../list/list-view-types";
import { KanbanQuickAddIssueButton, QuickAddIssueRoot } from "../quick-add";
import { KanbanIssueBlocksList } from "./blocks-list";

interface IKanbanGroup {
  groupId: string;
  issuesMap: IIssueMap;
  groupedIssueIds: TGroupedIssues | TSubGroupedIssues;
  displayProperties: IIssueDisplayProperties | undefined;
  sub_group_by: TIssueGroupByOptions | undefined;
  group_by: TIssueGroupByOptions | undefined;
  sub_group_id: string;
  isDragDisabled: boolean;
  isDropDisabled: boolean;
  dropErrorMessage: string | undefined;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  quickActions: TRenderQuickActions;
  enableQuickIssueCreate?: boolean;
  quickAddCallback?: (projectId: string | null | undefined, data: TIssue) => Promise<TIssue | undefined>;
  loadMoreIssues: (groupId?: string, subGroupId?: string) => void;
  disableIssueCreation?: boolean;
  canEditProperties: (projectId: string | undefined) => boolean;
  groupByVisibilityToggle?: boolean;
  scrollableContainerRef?: MutableRefObject<HTMLDivElement | null>;
  handleOnDrop: (source: GroupDropLocation, destination: GroupDropLocation) => Promise<void>;
  orderBy: TIssueOrderByOptions | undefined;
  isEpic?: boolean;
}

const prePopulateQuickAddData = (
  defaultStateId: string | undefined,
  groupByKey: string | undefined,
  subGroupByKey: string | undefined | null,
  groupValue: string,
  subGroupValue: string
) => {
  let preloadedData: object = { state_id: defaultStateId };

  if (groupByKey) {
    if (groupByKey === "state") {
      preloadedData = { ...preloadedData, state_id: groupValue };
    } else if (groupByKey === "priority") {
      preloadedData = { ...preloadedData, priority: groupValue };
    } else if (groupByKey === "cycle") {
      preloadedData = { ...preloadedData, cycle_id: groupValue };
    } else if (groupByKey === "module") {
      preloadedData = { ...preloadedData, module_ids: [groupValue] };
    } else if (groupByKey === "labels" && groupValue != "None") {
      preloadedData = { ...preloadedData, label_ids: [groupValue] };
    } else if (groupByKey === "assignees" && groupValue != "None") {
      preloadedData = { ...preloadedData, assignee_ids: [groupValue] };
    } else if (groupByKey === "created_by") {
      preloadedData = { ...preloadedData };
    } else {
      preloadedData = { ...preloadedData, [groupByKey]: groupValue };
    }
  }

  if (subGroupByKey) {
    if (subGroupByKey === "state") {
      preloadedData = { ...preloadedData, state_id: subGroupValue };
    } else if (subGroupByKey === "priority") {
      preloadedData = { ...preloadedData, priority: subGroupValue };
    } else if (subGroupByKey === "cycle") {
      preloadedData = { ...preloadedData, cycle_id: subGroupValue };
    } else if (subGroupByKey === "module") {
      preloadedData = { ...preloadedData, module_ids: [subGroupValue] };
    } else if (subGroupByKey === "labels" && subGroupValue != "None") {
      preloadedData = { ...preloadedData, label_ids: [subGroupValue] };
    } else if (subGroupByKey === "assignees" && subGroupValue != "None") {
      preloadedData = { ...preloadedData, assignee_ids: [subGroupValue] };
    } else if (subGroupByKey === "created_by") {
      preloadedData = { ...preloadedData };
    } else {
      preloadedData = { ...preloadedData, [subGroupByKey]: subGroupValue };
    }
  }

  return preloadedData;
};

type TKanbanGroupIssuesArgs = Pick<IKanbanGroup, "groupId" | "sub_group_id" | "groupedIssueIds"> &
  Pick<ReturnType<typeof useIssuesStore>["issues"], "getGroupIssueCount" | "getPaginationData">;

// Which work items the column shows, and whether more of them are still to be fetched.
const useKanbanGroupIssues = (args: TKanbanGroupIssuesArgs) => {
  const { groupId, sub_group_id, groupedIssueIds, getGroupIssueCount, getPaginationData } = args;

  const isSubGroup = !!sub_group_id && sub_group_id !== "null";

  const issueIds = isSubGroup
    ? ((groupedIssueIds as TSubGroupedIssues)?.[groupId]?.[sub_group_id] ?? [])
    : ((groupedIssueIds as TGroupedIssues)?.[groupId] ?? []);

  const groupIssueCount = getGroupIssueCount(groupId, sub_group_id, false) ?? 0;

  const nextPageResults = getPaginationData(groupId, sub_group_id)?.nextPageResults;

  const shouldLoadMore = nextPageResults === undefined ? issueIds?.length < groupIssueCount : !!nextPageResults;

  return { isSubGroup, issueIds, shouldLoadMore };
};

type TKanbanGroupLoadMoreProps = {
  isSubGroup: boolean;
  isPaginating: boolean;
  onLoadMore: () => void;
  setIntersectionElement: (element: HTMLSpanElement | null) => void;
};

// A sub-group asks before loading more; a column loads the next page when its loaders come into view.
function KanbanGroupLoadMore(props: TKanbanGroupLoadMoreProps) {
  const { isSubGroup, isPaginating, onLoadMore, setIntersectionElement } = props;
  const { t } = useTranslation();

  if (!isSubGroup)
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 2 }).map((_, index) => (
          // oxlint-disable-next-line react/no-array-index-key
          <KanbanIssueBlockLoader key={index} />
        ))}
        <KanbanIssueBlockLoader ref={setIntersectionElement} />
      </div>
    );

  if (isPaginating) return <KanbanIssueBlockLoader />;

  return (
    <button
      type="button"
      className="sticky bottom-0 w-full cursor-pointer p-3 text-left text-13 font-medium text-accent-primary hover:text-accent-secondary hover:underline"
      onClick={onLoadMore}
    >
      {t("common.load_more")} &darr;
    </button>
  );
}

type TKanbanGroupQuickAddProps = Pick<
  IKanbanGroup,
  "groupId" | "sub_group_id" | "group_by" | "sub_group_by" | "quickAddCallback" | "isEpic"
>;

const KanbanGroupQuickAdd = observer(function KanbanGroupQuickAdd(props: TKanbanGroupQuickAddProps) {
  const { groupId, sub_group_id, group_by, sub_group_by, quickAddCallback, isEpic = false } = props;
  // hooks
  const projectState = useProjectState();
  // derived values
  const defaultStateId = projectState.projectStates?.find((state) => state.default)?.id;

  return (
    <div className="sticky bottom-0 w-full bg-surface-2 py-0.5">
      <QuickAddIssueRoot
        layout={EIssueLayoutTypes.KANBAN}
        QuickAddButton={KanbanQuickAddIssueButton}
        prePopulatedData={{
          ...(group_by && prePopulateQuickAddData(defaultStateId, group_by, sub_group_by, groupId, sub_group_id)),
        }}
        quickAddCallback={quickAddCallback}
        isEpic={isEpic}
      />
    </div>
  );
});

type TKanbanGroupDragStateArgs = Pick<IKanbanGroup, "group_by" | "sub_group_by" | "orderBy" | "isDropDisabled"> & {
  isWorkflowDropDisabled: boolean;
  isDraggingOverColumn: boolean;
};

// Whether a drop here would be refused (and the overlay should say so), and whether cards can be dragged at all
// in the current grouping.
const getKanbanGroupDragState = (args: TKanbanGroupDragStateArgs) => {
  const { group_by, sub_group_by, orderBy, isDropDisabled, isWorkflowDropDisabled, isDraggingOverColumn } = args;
  const canOverlayBeVisible = isWorkflowDropDisabled || orderBy !== "sort_order" || isDropDisabled;
  const shouldOverlayBeVisible = isDraggingOverColumn && canOverlayBeVisible;
  const canDragIssuesInCurrentGrouping =
    !!group_by &&
    DRAG_ALLOWED_GROUPS.includes(group_by) &&
    (sub_group_by ? DRAG_ALLOWED_GROUPS.includes(sub_group_by) : true);
  return { canOverlayBeVisible, shouldOverlayBeVisible, canDragIssuesInCurrentGrouping };
};

export const KanbanGroup = observer(function KanbanGroup(props: IKanbanGroup) {
  const {
    groupId,
    sub_group_id,
    group_by,
    orderBy,
    sub_group_by,
    issuesMap,
    displayProperties,
    groupedIssueIds,
    isDropDisabled,
    dropErrorMessage,
    updateIssue,
    quickActions,
    canEditProperties,
    loadMoreIssues,
    enableQuickIssueCreate,
    disableIssueCreation,
    quickAddCallback,
    scrollableContainerRef,
    handleOnDrop,
    isEpic = false,
  } = props;
  // i18n
  const { t } = useTranslation();
  const {
    issues: { getGroupIssueCount, getPaginationData, getIssueLoader },
  } = useIssuesStore();

  const [intersectionElement, setIntersectionElement] = useState<HTMLSpanElement | null>(null);
  const columnRef = useRef<HTMLDivElement | null>(null);

  const containerRef = sub_group_by && scrollableContainerRef ? scrollableContainerRef : columnRef;

  const loadMoreIssuesInThisGroup = useCallback(() => {
    loadMoreIssues(groupId, sub_group_id === "null" ? undefined : sub_group_id);
  }, [loadMoreIssues, groupId, sub_group_id]);

  const isPaginating = !!getIssueLoader(groupId, sub_group_id);
  const { isSubGroup, issueIds, shouldLoadMore } = useKanbanGroupIssues({
    groupId,
    sub_group_id,
    groupedIssueIds,
    getGroupIssueCount,
    getPaginationData,
  });

  useIntersectionObserver(
    containerRef,
    isPaginating ? null : intersectionElement,
    loadMoreIssuesInThisGroup,
    `0% 100% 100% 100%`
  );
  const [isDraggingOverColumn, setIsDraggingOverColumn] = useState(false);

  const { workflowDisabledSource, isWorkflowDropDisabled, handleWorkFlowState, getIsWorkflowWorkItemCreationDisabled } =
    useWorkFlowFDragNDrop(group_by, sub_group_by);

  // Enable Kanban Columns as Drop Targets
  useEffect(() => {
    const element = columnRef.current;

    if (!element) return;

    return combine(
      dropTargetForElements({
        element,
        getData: () => ({ groupId, subGroupId: sub_group_id, columnId: `${groupId}__${sub_group_id}`, type: "COLUMN" }),
        onDragEnter: (payload) => {
          const source = getSourceFromDropPayload(payload);
          setIsDraggingOverColumn(true);
          // handle if dragging a workflowState
          if (source) {
            handleWorkFlowState(source?.groupId, groupId, source?.subGroupId, sub_group_id);
          }
        },
        onDragLeave: () => {
          setIsDraggingOverColumn(false);
        },
        onDragStart: (payload) => {
          const source = getSourceFromDropPayload(payload);
          setIsDraggingOverColumn(true);
          // handle if dragging a workflowState
          if (source) {
            handleWorkFlowState(source?.groupId, groupId, source?.subGroupId, sub_group_id);
          }
        },
        onDrop: (payload) => {
          setIsDraggingOverColumn(false);
          const source = getSourceFromDropPayload(payload);
          const destination = getDestinationFromDropPayload(payload);

          if (!source || !destination) return;

          if ((isWorkflowDropDisabled || isDropDisabled) && dropErrorMessage) {
            setToast({
              type: "warning",
              title: t("common.warning"),
              message: dropErrorMessage,
            });
            return;
          }

          handleOnDrop(source, destination);

          highlightIssueOnDrop(
            getIssueBlockId(source.id, destination?.groupId, destination?.subGroupId),
            orderBy !== "sort_order"
          );
        },
      }),
      autoScrollForElements({
        element,
      })
    );
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [
    columnRef,
    groupId,
    sub_group_id,
    setIsDraggingOverColumn,
    orderBy,
    isDropDisabled,
    isWorkflowDropDisabled,
    dropErrorMessage,
    handleOnDrop,
  ]);

  const { canOverlayBeVisible, shouldOverlayBeVisible, canDragIssuesInCurrentGrouping } = getKanbanGroupDragState({
    group_by,
    sub_group_by,
    orderBy,
    isDropDisabled,
    isWorkflowDropDisabled,
    isDraggingOverColumn,
  });

  return (
    <div
      id={`${groupId}__${sub_group_id}`}
      className={cn(
        "relative h-full min-h-[120px] transition-all",
        { "rounded-sm bg-layer-1": isDraggingOverColumn },
        { "vertical-scrollbar scrollbar-md": !sub_group_by && !shouldOverlayBeVisible }
      )}
      ref={columnRef}
    >
      <GroupDragOverlay
        dragColumnOrientation={sub_group_by ? "justify-start" : "justify-center"}
        canOverlayBeVisible={canOverlayBeVisible}
        isDropDisabled={isWorkflowDropDisabled || isDropDisabled}
        workflowDisabledSource={workflowDisabledSource}
        dropErrorMessage={dropErrorMessage}
        orderBy={orderBy}
        isDraggingOverColumn={isDraggingOverColumn}
        isEpic={isEpic}
      />
      <KanbanIssueBlocksList
        sub_group_id={sub_group_id}
        groupId={groupId}
        issuesMap={issuesMap}
        issueIds={issueIds || []}
        displayProperties={displayProperties}
        updateIssue={updateIssue}
        quickActions={quickActions}
        canEditProperties={canEditProperties}
        scrollableContainerRef={scrollableContainerRef}
        canDropOverIssue={!canOverlayBeVisible}
        canDragIssuesInCurrentGrouping={canDragIssuesInCurrentGrouping}
        isEpic={isEpic}
      />

      {shouldLoadMore && (
        <KanbanGroupLoadMore
          isSubGroup={isSubGroup}
          isPaginating={isPaginating}
          onLoadMore={loadMoreIssuesInThisGroup}
          setIntersectionElement={setIntersectionElement}
        />
      )}

      {enableQuickIssueCreate &&
        !disableIssueCreation &&
        !getIsWorkflowWorkItemCreationDisabled(groupId, sub_group_id) && (
          <KanbanGroupQuickAdd
            groupId={groupId}
            sub_group_id={sub_group_id}
            group_by={group_by}
            sub_group_by={sub_group_by}
            quickAddCallback={quickAddCallback}
            isEpic={isEpic}
          />
        )}
    </div>
  );
});
