/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import type { TRecharts } from "../use-recharts";
import { useRecharts } from "../use-recharts";
// plane imports
import type { TreeMapChartProps } from "@plane/types";
import { cn } from "@plane/utils";
// local imports
import { CustomTreeMapContent } from "./map-content";
import { TreeMapTooltip } from "./tooltip";

const TreeMapChartContent = React.memo(function TreeMapChartContent(
  props: TreeMapChartProps & { recharts: TRecharts }
) {
  const { Treemap, ResponsiveContainer, Tooltip } = props.recharts;
  const { data, className = "w-full h-96", isAnimationActive = false, showTooltip = true } = props;
  return (
    <div className={cn(className)}>
      <ResponsiveContainer width="100%" height="100%">
        <Treemap
          data={data}
          nameKey="name"
          dataKey="value"
          stroke="transparent"
          className="cursor-pointer bg-layer-1"
          content={<CustomTreeMapContent />}
          animationEasing="ease-out"
          isUpdateAnimationActive={isAnimationActive}
          animationBegin={100}
          animationDuration={500}
        >
          {showTooltip && (
            <Tooltip
              content={({ active, payload }) => <TreeMapTooltip active={active} payload={payload} />}
              cursor={{
                fill: "currentColor",
                className: "bg-layer-1 cursor-pointer",
              }}
              wrapperStyle={{
                pointerEvents: "auto",
              }}
            />
          )}
        </Treemap>
      </ResponsiveContainer>
    </div>
  );
});
TreeMapChartContent.displayName = "TreeMapChartContent";

export const TreeMapChart = React.memo(function TreeMapChart(props: TreeMapChartProps) {
  const recharts = useRecharts();
  // until recharts has loaded, hold the chart's place so the layout does not jump
  if (!recharts) return <div className={props.className} />;
  return <TreeMapChartContent {...props} recharts={recharts} />;
});

TreeMapChart.displayName = "TreeMapChart";
