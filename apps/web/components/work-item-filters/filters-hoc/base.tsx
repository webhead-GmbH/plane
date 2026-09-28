/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import { v4 as uuidv4 } from "uuid";
// plane imports
import type { TSaveViewOptions, TUpdateViewOptions } from "@plane/constants";
import type { IWorkItemFilterInstance } from "@plane/shared-state";
import type { IIssueFilters, TWorkItemFilterExpression } from "@plane/types";
// store hooks
import { useWorkItemFilters } from "@/hooks/store/work-item-filters/use-work-item-filters";
// plane web imports
import type { TWorkItemFiltersEntityProps } from "@/hooks/work-item-filters/use-work-item-filters-config";
import { useWorkItemFiltersConfig } from "@/hooks/work-item-filters/use-work-item-filters-config";
// local imports
import type { TSharedWorkItemFiltersHOCProps, TSharedWorkItemFiltersProps } from "./shared";

type TAdditionalWorkItemFiltersProps = {
  saveViewOptions?: TSaveViewOptions<TWorkItemFilterExpression>;
  updateViewOptions?: TUpdateViewOptions<TWorkItemFilterExpression>;
} & TWorkItemFiltersEntityProps;

type TWorkItemFiltersHOCProps = TSharedWorkItemFiltersHOCProps & TAdditionalWorkItemFiltersProps;

export const WorkItemFiltersHOC = observer(function WorkItemFiltersHOC(props: TWorkItemFiltersHOCProps) {
  const { children, initialWorkItemFilters } = props;

  // Only initialize filter instance when initial work item filters are defined
  if (!initialWorkItemFilters)
    return <>{typeof children === "function" ? children({ filter: undefined }) : children}</>;

  return (
    <WorkItemFilterRoot {...props} initialWorkItemFilters={initialWorkItemFilters}>
      {children}
    </WorkItemFilterRoot>
  );
});

type TWorkItemFilterProps = TSharedWorkItemFiltersProps &
  TAdditionalWorkItemFiltersProps & {
    initialWorkItemFilters: IIssueFilters;
    children: React.ReactNode | ((props: { filter: IWorkItemFilterInstance }) => React.ReactNode);
  };

const WorkItemFilterRoot = observer(function WorkItemFilterRoot(props: TWorkItemFilterProps) {
  const {
    children,
    entityType,
    entityId,
    filtersToShowByLayout,
    initialWorkItemFilters,
    isTemporary,
    saveViewOptions,
    updateFilters,
    updateViewOptions,
    showOnMount,
    ...entityConfigProps
  } = props;
  // store hooks
  const { buildFilter, registerFilter, deleteFilter } = useWorkItemFilters();
  // states
  const [adoptedFilter, setAdoptedFilter] = useState<{
    builtFilter: IWorkItemFilterInstance;
    filter: IWorkItemFilterInstance;
  }>();
  // derived values
  const workItemEntityID = useMemo(
    () => (isTemporary ? `TEMP-${entityId ?? uuidv4()}` : entityId),
    [isTemporary, entityId]
  );
  // memoize initial values to prevent re-computations when reference changes
  const initialUserFilters = useMemo(() => initialWorkItemFilters.richFilters, [initialWorkItemFilters]);
  const workItemFiltersConfig = useWorkItemFiltersConfig({
    allowedFilters: filtersToShowByLayout ? filtersToShowByLayout : [],
    ...entityConfigProps,
  });
  // build the filter instance, and the parameters the store needs to adopt it
  const filterParams = useMemo(
    () => ({
      entityType,
      entityId: workItemEntityID,
      initialExpression: initialUserFilters,
      onExpressionChange: updateFilters,
      expressionOptions: {
        saveViewOptions,
        updateViewOptions,
      },
      showOnMount,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [entityType, workItemEntityID, saveViewOptions, updateViewOptions, updateFilters]
  );
  const builtFilter = useMemo(() => buildFilter(filterParams), [buildFilter, filterParams]);
  // Putting the instance in the store is a write to an observable map, and writing it while
  // rendering would update the header's filters toggle in the middle of this render, which React
  // refuses. So the instance is built here and the store adopts it from an effect. The store keeps
  // the instance it already holds for the entity, and that one, not ours, is what the children get.
  const workItemLayoutFilter = adoptedFilter?.builtFilter === builtFilter ? adoptedFilter.filter : builtFilter;

  useEffect(() => {
    const registeredFilter = registerFilter({ ...filterParams, filter: builtFilter });
    if (registeredFilter !== builtFilter) setAdoptedFilter({ builtFilter, filter: registeredFilter });
  }, [builtFilter, filterParams, registerFilter]);

  // delete filter instance when component unmounts
  useEffect(
    () => () => {
      deleteFilter(entityType, workItemEntityID);
    },
    [deleteFilter, entityType, workItemEntityID]
  );

  useEffect(() => {
    workItemLayoutFilter.configManager.setAreConfigsReady(workItemFiltersConfig.areAllConfigsInitialized);
    workItemLayoutFilter.configManager.registerAll(workItemFiltersConfig.configs);
  }, [
    workItemFiltersConfig.areAllConfigsInitialized,
    workItemFiltersConfig.configs,
    workItemLayoutFilter.configManager,
  ]);

  return <>{typeof children === "function" ? children({ filter: workItemLayoutFilter }) : children}</>;
});
