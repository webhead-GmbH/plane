/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo } from "react";
import { sortBy } from "lodash-es";
import { observer } from "mobx-react";
// components
import { FilterMembersList } from "@/components/common/filters/members-list";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useUser } from "@/hooks/store/user";

type Props = {
  appliedFilters: string[] | null;
  handleUpdate: (val: string) => void;
  memberIds: string[] | undefined;
  searchQuery: string;
};

export const FilterCreatedBy = observer(function FilterCreatedBy(props: Props) {
  const { appliedFilters, handleUpdate, memberIds, searchQuery } = props;
  // store hooks
  const { getUserDetails } = useMember();
  const { data: currentUser } = useUser();

  const sortedOptions = useMemo(() => {
    const filteredOptions = (memberIds || []).filter((memberId) =>
      getUserDetails(memberId)?.display_name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return sortBy(filteredOptions, [
      (memberId) => !(appliedFilters ?? []).includes(memberId),
      (memberId) => memberId !== currentUser?.id,
      (memberId) => getUserDetails(memberId)?.display_name.toLowerCase(),
    ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  return (
    <FilterMembersList
      title="Created by"
      appliedFilters={appliedFilters}
      handleUpdate={handleUpdate}
      sortedOptions={sortedOptions}
    />
  );
});
