/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import { useRecharts } from "../use-recharts";
import type { PieSectorDataItem } from "recharts/types/polar/Pie";

export const CustomActiveShape = React.memo(function CustomActiveShape(props: PieSectorDataItem) {
  const { cx, cy, cornerRadius, innerRadius, outerRadius, startAngle, endAngle, fill } = props;
  // the pie chart renders only once recharts has loaded, so this has the module from the first render
  const recharts = useRecharts();

  if (!recharts) return null;
  const { Sector } = recharts;

  return (
    <g>
      <Sector
        cx={cx}
        cy={cy}
        innerRadius={innerRadius}
        outerRadius={outerRadius}
        cornerRadius={cornerRadius}
        startAngle={startAngle}
        endAngle={endAngle}
        fill={fill}
      />
      <Sector
        cx={cx}
        cy={cy}
        startAngle={startAngle}
        endAngle={endAngle}
        cornerRadius={cornerRadius}
        innerRadius={(outerRadius ?? 0) + 6}
        outerRadius={(outerRadius ?? 0) + 10}
        fill={fill}
      />
    </g>
  );
});
