/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
// plane imports
import { Button } from "@plane/propel/button";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";

type TProps = {
  isOpen: boolean;
  personName: string;
  monthLabel: string;
  isBusy: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
};

/**
 * Reopening a closed month, which cannot be done without saying why.
 *
 * The reason is required rather than encouraged. A closed month is what gets
 * handed to the payroll accountant, and one that quietly reopened is one nobody
 * can account for afterwards — so the button stays disabled until there is
 * something to record alongside it.
 */
export const HrReopenModal = ({ isOpen, personName, monthLabel, isBusy, onClose, onConfirm }: TProps) => {
  const [reason, setReason] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setReason("");
    // Focus belongs inside the dialog once it opens, or a keyboard user is left
    // tabbing from wherever they were on the page behind it.
    field.current?.focus();
  }, [isOpen]);

  const canConfirm = reason.trim().length > 0 && !isBusy;

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XL}>
      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-start gap-3">
          <span className="bg-amber-500/15 flex size-9 flex-shrink-0 items-center justify-center rounded-full">
            <AlertTriangle className="text-amber-600 size-4" />
          </span>
          <div className="flex flex-col gap-1">
            <h3 className="text-custom-text-100 text-lg font-medium">Reopen {monthLabel}?</h3>
            <p className="text-custom-text-300 text-sm">
              {personName}&apos;s month has been closed and its figures frozen. Reopening keeps the closed version and
              records this one alongside it — nothing that was agreed is overwritten.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="hr-reopen-reason" className="text-custom-text-200 text-sm font-medium">
            Why is it being reopened?
          </label>
          <textarea
            id="hr-reopen-reason"
            ref={field}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            placeholder="Three days in the second week were logged against the wrong month."
            className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 placeholder:text-custom-text-400 focus:border-custom-primary-100 text-sm w-full resize-none rounded-md border px-3 py-2 outline-none"
          />
        </div>

        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Leave it closed
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!canConfirm}
            loading={isBusy}
            onClick={() => onConfirm(reason.trim())}
          >
            Reopen
          </Button>
        </div>
      </div>
    </ModalCore>
  );
};
