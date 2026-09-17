/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { Combobox } from "@headlessui/react";
// plane imports
import { Loader } from "@plane/ui";

type Props = {
  isSearching: boolean;
  children: ReactNode;
};

export function IssueSearchModalOptions(props: Props) {
  const { isSearching, children } = props;

  return (
    <Combobox.Options as="ul" static className="max-h-80 scroll-py-2 divide-y divide-subtle-1 overflow-y-auto">
      {isSearching ? (
        <Loader className="space-y-3 p-3">
          <Loader.Item height="40px" />
          <Loader.Item height="40px" />
          <Loader.Item height="40px" />
          <Loader.Item height="40px" />
        </Loader>
      ) : (
        children
      )}
    </Combobox.Options>
  );
}
