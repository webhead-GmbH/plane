/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ChevronLeft, ChevronRight } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";

type TProps = {
  /** What is being stepped through, already formatted — a month or a year. */
  label: string;
  onPrevious: () => void;
  onNext: () => void;
  previousLabel?: string;
  nextLabel?: string;
};

/**
 * Stepping back and forward through a period.
 *
 * The single most-used control in the module, and it had been built four
 * different ways: labelled secondary buttons here, ghost chevrons there, bare
 * chevrons somewhere else. Somebody moving between two screens had to find the
 * same control twice.
 *
 * Chevrons rather than words, because "Earlier" and "Later" read as buttons that
 * do something to the month rather than ones that change which month is shown.
 */
export const HrPeriodStepper = ({ label, onPrevious, onNext, previousLabel, nextLabel }: TProps) => {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={onPrevious}
        aria-label={previousLabel ?? t("hr.my_time.previous_month")}
        className="grid size-7 place-items-center rounded-md text-tertiary transition-colors hover:bg-layer-2 hover:text-primary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
      >
        <ChevronLeft className="size-4" />
      </button>
      <span className="min-w-40 text-center text-13 font-medium text-primary">{label}</span>
      <button
        type="button"
        onClick={onNext}
        aria-label={nextLabel ?? t("hr.my_time.next_month")}
        className="grid size-7 place-items-center rounded-md text-tertiary transition-colors hover:bg-layer-2 hover:text-primary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
      >
        <ChevronRight className="size-4" />
      </button>
    </div>
  );
};
