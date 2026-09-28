/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// components
import { AppliedMembersFilters as CommonAppliedMembersFilters } from "@/components/common/applied-filters/members";

type Props = {
  handleRemove: (val: string) => void;
  values: string[];
  editable: boolean | undefined;
};

export const AppliedMembersFilters = observer(function AppliedMembersFilters(props: Props) {
  const { handleRemove, values, editable } = props;

  return <CommonAppliedMembersFilters handleRemove={handleRemove} values={values} editable={editable} compact />;
});
