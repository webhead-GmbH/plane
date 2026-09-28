/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { MutableRefObject } from "react";
import { useEffect, useRef, useState } from "react";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import { dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { observer } from "mobx-react";
// plane imports
import { DRAG_ALLOWED_GROUPS } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { setToast } from "@plane/blocks/toast";
import type {
  IGroupByColumn,
  TIssueMap,
  TIssueGroupByOptions,
  TIssueOrderByOptions,
  TIssue,
  IIssueDisplayProperties,
  TIssueKanbanFilters,
} from "@plane/types";
import { EIssueLayoutTypes } from "@plane/types";
import { Row } from "@plane/blocks/layout";
import { cn } from "@plane/utils";
// components
import { ListLoaderItemRow } from "@/components/ui/loader/layouts/list-layout-loader";
import { useWorkFlowFDragNDrop } from "@/components/workflow";
// hooks
import { useProjectState } from "@/hooks/store/use-project-state";
import { useIntersectionObserver } from "@/hooks/use-intersection-observer";
import { useIssuesStore } from "@/hooks/use-issue-layout-store";
import type { TSelectionHelper } from "@/hooks/use-multiple-select";
// local imports
import { GroupDragOverlay } from "../group-drag-overlay";
import { ListQuickAddIssueButton, QuickAddIssueRoot } from "../quick-add";
import type { GroupDropLocation } from "../utils";
import {
  getDestinationFromDropPayload,
  getIssueBlockId,
  getSourceFromDropPayload,
  highlightIssueOnDrop,
} from "../utils";
import { IssueBlocksList } from "./blocks-list";
import { HeaderGroupByCard } from "./headers/group-by-card";
import type { TRenderQuickActions } from "./list-view-types";

interface Props {
  groupIssueIds: string[] | undefined;
  group: IGroupByColumn;
  issuesMap: TIssueMap;
  group_by: TIssueGroupByOptions | null;
  orderBy: TIssueOrderByOptions | undefined;
  getGroupIndex: (groupId: string | undefined) => number;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  quickActions: TRenderQuickActions;
  displayProperties: IIssueDisplayProperties | undefined;
  enableIssueQuickAdd: boolean;
  canEditProperties: (projectId: string | undefined) => boolean;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  quickAddCallback?: ((projectId: string | null | undefined, data: TIssue) => Promise<TIssue | undefined>) | undefined;
  handleOnDrop: (source: GroupDropLocation, destination: GroupDropLocation) => Promise<void>;
  disableIssueCreation?: boolean;
  addIssuesToView?: (issueIds: string[]) => Promise<TIssue>;
  isCompletedCycle?: boolean;
  showEmptyGroup?: boolean;
  loadMoreIssues: (groupId?: string) => void;
  selectionHelpers: TSelectionHelper;
  handleCollapsedGroups: (value: string) => void;
  collapsedGroups: TIssueKanbanFilters;
  isEpic?: boolean;
}

const prePopulateQuickAddData = (defaultStateId: string | undefined, groupByKey: string | null, value: any) => {
  let preloadedData: object = { state_id: defaultStateId };

  if (groupByKey === null) {
    preloadedData = { ...preloadedData };
  } else {
    if (groupByKey === "state") {
      preloadedData = { ...preloadedData, state_id: value };
    } else if (groupByKey === "priority") {
      preloadedData = { ...preloadedData, priority: value };
    } else if (groupByKey === "labels" && value != "None") {
      preloadedData = { ...preloadedData, label_ids: [value] };
    } else if (groupByKey === "assignees" && value != "None") {
      preloadedData = { ...preloadedData, assignee_ids: [value] };
    } else if (groupByKey === "cycle" && value != "None") {
      preloadedData = { ...preloadedData, cycle_id: value };
    } else if (groupByKey === "module" && value != "None") {
      preloadedData = { ...preloadedData, module_ids: [value] };
    } else if (groupByKey === "created_by") {
      preloadedData = { ...preloadedData };
    } else {
      preloadedData = { ...preloadedData, [groupByKey]: value };
    }
  }

  return preloadedData;
};

type TListGroupPaginationArgs = {
  groupId: string;
  groupIssueIds: string[] | undefined;
  containerRef: Props["containerRef"];
  intersectionElement: HTMLDivElement | null;
  loadMoreIssues: Props["loadMoreIssues"];
};

// How many work items the group has, whether a page is loading, and whether more are still to come.
// The next page loads when the group's last loader row comes into view.
const useListGroupPagination = (args: TListGroupPaginationArgs) => {
  const { groupId, groupIssueIds, containerRef, intersectionElement, loadMoreIssues } = args;
  const {
    issues: { getGroupIssueCount, getPaginationData, getIssueLoader },
  } = useIssuesStore();

  const groupIssueCount = getGroupIssueCount(groupId, undefined, false) ?? 0;
  const nextPageResults = getPaginationData(groupId, undefined)?.nextPageResults;
  const isPaginating = !!getIssueLoader(groupId);

  useIntersectionObserver(containerRef, isPaginating ? null : intersectionElement, loadMoreIssues, `100% 0% 100% 0%`);

  const shouldLoadMore =
    nextPageResults === undefined && groupIssueCount !== undefined && groupIssueIds
      ? groupIssueIds.length < groupIssueCount
      : !!nextPageResults;

  return { groupIssueCount, isPaginating, shouldLoadMore };
};

type TListGroupLoadMoreProps = {
  groupId: string;
  isGrouped: boolean;
  isPaginating: boolean;
  loadMoreIssues: Props["loadMoreIssues"];
  setIntersectionElement: (element: HTMLDivElement | null) => void;
};

// A grouped list asks before loading more; an ungrouped one loads the next page when its loaders come into view.
function ListGroupLoadMore(props: TListGroupLoadMoreProps) {
  const { groupId, isGrouped, isPaginating, loadMoreIssues, setIntersectionElement } = props;
  const { t } = useTranslation();

  if (!isGrouped)
    return (
      <>
        {Array.from({ length: 2 }).map((_, index) => (
          // oxlint-disable-next-line react/no-array-index-key
          <ListLoaderItemRow key={index} />
        ))}
        <ListLoaderItemRow ref={setIntersectionElement} />
      </>
    );

  if (isPaginating) return <ListLoaderItemRow />;

  return (
    <button
      type="button"
      className={
        "relative flex h-11 w-full cursor-pointer items-center gap-3 border border-transparent border-t-subtle-1 bg-surface-1 p-3 pl-8 text-left text-13 font-medium text-accent-primary hover:text-accent-secondary hover:underline"
      }
      onClick={() => loadMoreIssues(groupId)}
    >
      {t("common.load_more")} &darr;
    </button>
  );
}

type TListGroupQuickAddProps = {
  groupId: string;
  group_by: Props["group_by"];
  isEnabled: boolean;
  disableIssueCreation?: boolean;
  isGroupByCreatedBy: boolean;
  isCompletedCycle?: boolean;
  isWorkflowIssueCreationDisabled: boolean;
  quickAddCallback: Props["quickAddCallback"];
  isEpic: boolean;
};

const ListGroupQuickAdd = observer(function ListGroupQuickAdd(props: TListGroupQuickAddProps) {
  const {
    groupId,
    group_by,
    isEnabled,
    disableIssueCreation,
    isGroupByCreatedBy,
    isCompletedCycle,
    isWorkflowIssueCreationDisabled,
    quickAddCallback,
    isEpic,
  } = props;
  // hooks
  const projectState = useProjectState();

  if (!isEnabled || disableIssueCreation || isGroupByCreatedBy || isCompletedCycle || isWorkflowIssueCreationDisabled)
    return null;

  // derived values
  const defaultStateId = projectState.projectStates?.find((state) => state.default)?.id;

  return (
    <div className="sticky bottom-0 z-[1] w-full flex-shrink-0">
      <QuickAddIssueRoot
        layout={EIssueLayoutTypes.LIST}
        QuickAddButton={ListQuickAddIssueButton}
        prePopulatedData={prePopulateQuickAddData(defaultStateId, group_by, groupId)}
        containerClassName="border-b border-t border-subtle bg-surface-1 "
        quickAddCallback={quickAddCallback}
        isEpic={isEpic}
      />
    </div>
  );
});

type TListGroupDragStateArgs = Pick<Props, "group_by" | "orderBy"> & {
  isGroupDropDisabled: boolean;
  isWorkflowDropDisabled: boolean;
};

// Whether work items can be dragged in this grouping, and whether a drop on this group would be refused.
const getListGroupDragState = (args: TListGroupDragStateArgs) => {
  const { group_by, orderBy, isGroupDropDisabled, isWorkflowDropDisabled } = args;
  return {
    isDragAllowed: group_by ? DRAG_ALLOWED_GROUPS.includes(group_by) : true,
    canOverlayBeVisible: isWorkflowDropDisabled || orderBy !== "sort_order" || isGroupDropDisabled,
    isDropDisabled: isWorkflowDropDisabled || isGroupDropDisabled,
  };
};

export const ListGroup = observer(function ListGroup(props: Props) {
  const {
    groupIssueIds = [],
    group,
    issuesMap,
    group_by,
    orderBy,
    getGroupIndex,
    updateIssue,
    quickActions,
    displayProperties,
    enableIssueQuickAdd,
    canEditProperties,
    containerRef,
    quickAddCallback,
    handleOnDrop,
    disableIssueCreation,
    addIssuesToView,
    isCompletedCycle,
    showEmptyGroup,
    loadMoreIssues,
    selectionHelpers,
    handleCollapsedGroups,
    collapsedGroups,
    isEpic = false,
  } = props;

  const [isDraggingOverColumn, setIsDraggingOverColumn] = useState(false);
  const [dragColumnOrientation, setDragColumnOrientation] = useState<"justify-start" | "justify-end">("justify-start");
  const isExpanded = !collapsedGroups?.group_by.includes(group.id);
  const groupRef = useRef<HTMLDivElement | null>(null);
  const { t } = useTranslation();

  const [intersectionElement, setIntersectionElement] = useState<HTMLDivElement | null>(null);

  const { workflowDisabledSource, isWorkflowDropDisabled, handleWorkFlowState, getIsWorkflowWorkItemCreationDisabled } =
    useWorkFlowFDragNDrop(group_by);
  const isWorkflowIssueCreationDisabled = getIsWorkflowWorkItemCreationDisabled(group.id);

  const { groupIssueCount, isPaginating, shouldLoadMore } = useListGroupPagination({
    groupId: group.id,
    groupIssueIds,
    containerRef,
    intersectionElement,
    loadMoreIssues,
  });

  const validateEmptyIssueGroups = (issueCount: number = 0) => {
    if (!showEmptyGroup && issueCount <= 0) return false;
    return true;
  };

  useEffect(() => {
    const element = groupRef.current;

    if (!element) return;

    return combine(
      dropTargetForElements({
        element,
        getData: () => ({ groupId: group.id, type: "COLUMN" }),
        onDragEnter: () => {
          setIsDraggingOverColumn(true);
        },
        onDragLeave: () => {
          setIsDraggingOverColumn(false);
        },
        onDragStart: () => {
          setIsDraggingOverColumn(true);
        },
        onDrag: ({ source }) => {
          const sourceGroupId = source?.data?.groupId as string | undefined;
          const currentGroupId = group.id;

          // oxlint-disable-next-line no-unused-expressions
          sourceGroupId && handleWorkFlowState(sourceGroupId, currentGroupId);

          const sourceIndex = getGroupIndex(sourceGroupId);
          const currentIndex = getGroupIndex(currentGroupId);

          if (sourceIndex > currentIndex) {
            setDragColumnOrientation("justify-end");
          } else {
            setDragColumnOrientation("justify-start");
          }
        },
        onDrop: (payload) => {
          setIsDraggingOverColumn(false);
          const source = getSourceFromDropPayload(payload);
          const destination = getDestinationFromDropPayload(payload);

          if (!source || !destination) return;

          if (isWorkflowDropDisabled || group.isDropDisabled) {
            if (group.dropErrorMessage)
              setToast({
                type: "warning",
                title: t("common.warning"),
                message: group.dropErrorMessage,
              });
            return;
          }

          handleOnDrop(source, destination);

          highlightIssueOnDrop(getIssueBlockId(source.id, destination?.groupId), orderBy !== "sort_order");

          if (!isExpanded) {
            handleCollapsedGroups(group.id);
          }
        },
      })
    );
  }, [
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
    groupRef?.current,
    group,
    orderBy,
    getGroupIndex,
    setDragColumnOrientation,
    setIsDraggingOverColumn,
    isWorkflowDropDisabled,
  ]);

  const { isDragAllowed, canOverlayBeVisible, isDropDisabled } = getListGroupDragState({
    group_by,
    orderBy,
    isGroupDropDisabled: !!group.isDropDisabled,
    isWorkflowDropDisabled,
  });

  const isGroupByCreatedBy = group_by === "created_by";
  const shouldExpand = (!!groupIssueCount && isExpanded) || !group_by;

  return validateEmptyIssueGroups(groupIssueCount) ? (
    <div
      ref={groupRef}
      className={cn(`relative flex flex-shrink-0 flex-col`, {
        "border-accent-strong": isDraggingOverColumn,
        "border-danger-subtle": isDraggingOverColumn && isDropDisabled,
      })}
    >
      <Row
        className={cn("w-full flex-shrink-0 border-b border-subtle bg-layer-1 py-1 pr-3 hover:bg-layer-1-hover", {
          "sticky top-0 z-[2]": isExpanded && groupIssueCount > 0,
        })}
      >
        <HeaderGroupByCard
          groupID={group.id}
          groupBy={group_by}
          icon={group.icon}
          title={group.name}
          count={groupIssueCount}
          issuePayload={group.payload}
          canEditProperties={canEditProperties}
          disableIssueCreation={
            disableIssueCreation || isGroupByCreatedBy || isCompletedCycle || isWorkflowIssueCreationDisabled
          }
          addIssuesToView={addIssuesToView}
          selectionHelpers={selectionHelpers}
          handleCollapsedGroups={handleCollapsedGroups}
          isEpic={isEpic}
        />
      </Row>
      {shouldExpand && (
        <div className="relative">
          <GroupDragOverlay
            dragColumnOrientation={dragColumnOrientation}
            canOverlayBeVisible={canOverlayBeVisible}
            isDropDisabled={isDropDisabled}
            workflowDisabledSource={workflowDisabledSource}
            dropErrorMessage={group.dropErrorMessage}
            orderBy={orderBy}
            isDraggingOverColumn={isDraggingOverColumn}
            isEpic={isEpic}
          />
          {groupIssueIds && (
            <IssueBlocksList
              issueIds={groupIssueIds}
              groupId={group.id}
              issuesMap={issuesMap}
              updateIssue={updateIssue}
              quickActions={quickActions}
              displayProperties={displayProperties}
              canEditProperties={canEditProperties}
              containerRef={containerRef}
              isDragAllowed={isDragAllowed}
              canDropOverIssue={!canOverlayBeVisible}
              selectionHelpers={selectionHelpers}
              isEpic={isEpic}
            />
          )}

          {shouldLoadMore && (
            <ListGroupLoadMore
              groupId={group.id}
              isGrouped={!!group_by}
              isPaginating={isPaginating}
              loadMoreIssues={loadMoreIssues}
              setIntersectionElement={setIntersectionElement}
            />
          )}

          <ListGroupQuickAdd
            groupId={group.id}
            group_by={group_by}
            isEnabled={!!enableIssueQuickAdd}
            disableIssueCreation={disableIssueCreation}
            isGroupByCreatedBy={isGroupByCreatedBy}
            isCompletedCycle={isCompletedCycle}
            isWorkflowIssueCreationDisabled={isWorkflowIssueCreationDisabled}
            quickAddCallback={quickAddCallback}
            isEpic={isEpic}
          />
        </div>
      )}
    </div>
  ) : null;
});
