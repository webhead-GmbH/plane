/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import useSWR from "swr";
// plane imports
import { Loader } from "@plane/blocks/skeleton";
// local imports
import { HrService } from "@/services/hr.service";

const hrService = new HrService();

/**
 * Whether the signed-in person runs HR, asked once and shared.
 *
 * The sidebar renders on every page, so this must not be the month view's own
 * request: that one refuses anybody without an employment record and rebuilds the
 * month on the way in.
 */
export const useHrAccess = () =>
  useSWR("HR_ACCESS", () => hrService.access(), { revalidateOnFocus: false, shouldRetryOnError: false });

/** Its children, for whoever runs HR only; nothing while the answer is on its way. */
export function HrManagerOnly({ children }: { children: ReactNode }) {
  const { data } = useHrAccess();
  return data?.is_hr_manager ? <>{children}</> : null;
}

/**
 * A page for whoever runs HR, and `refused` for everybody else.
 *
 * Some of what these pages read is open to every employee — their own record, the
 * holiday calendar their month is measured against — so the server's answers alone
 * do not keep the pages to the people who run HR. If the question itself fails,
 * the page renders and the server has the last word on every change.
 */
export function HrManagerPage({ children, refused }: { children: ReactNode; refused: ReactNode }) {
  const { data, error } = useHrAccess();

  if (error || data?.is_hr_manager) return <>{children}</>;
  if (data) return <>{refused}</>;
  return (
    <Loader className="flex w-full flex-col gap-7">
      <Loader.Item height="48px" />
      <Loader.Item height="280px" />
    </Loader>
  );
}
