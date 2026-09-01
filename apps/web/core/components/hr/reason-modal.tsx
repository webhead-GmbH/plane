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
  title: string;
  body: string;
  label: string;
  placeholder: string;
  confirmLabel: string;
  cancelLabel: string;
  isBusy: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
};

/**
 * Undoing something that has already been agreed, which cannot be done silently.
 *
 * Reopening a closed month and unpicking an applied import are the same act:
 * both put back something the figures already depended on. The reason is
 * required rather than encouraged, because a record that changed for no stated
 * reason is one nobody can account for afterwards — so the button stays disabled
 * until there is something to keep alongside it.
 */
export const HrReasonModal = ({
  isOpen,
  title,
  body,
  label,
  placeholder,
  confirmLabel,
  cancelLabel,
  isBusy,
  onClose,
  onConfirm,
}: TProps) => {
  const [reason, setReason] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setReason("");
    // Focus belongs inside the dialog once it opens, or a keyboard user is left
    // tabbing from wherever they were on the page behind it.
    field.current?.focus();
  }, [isOpen]);

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XL}>
      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-start gap-3">
          <span className="bg-amber-500/15 flex size-9 flex-shrink-0 items-center justify-center rounded-full">
            <AlertTriangle className="text-amber-600 size-4" />
          </span>
          <div className="flex flex-col gap-1">
            <h3 className="text-custom-text-100 text-lg font-medium">{title}</h3>
            <p className="text-custom-text-300 text-sm">{body}</p>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="hr-reason" className="text-custom-text-200 text-sm font-medium">
            {label}
          </label>
          <textarea
            id="hr-reason"
            ref={field}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            placeholder={placeholder}
            className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 placeholder:text-custom-text-400 focus:border-custom-primary-100 text-sm w-full resize-none rounded-md border px-3 py-2 outline-none"
          />
        </div>

        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={reason.trim().length === 0 || isBusy}
            loading={isBusy}
            onClick={() => onConfirm(reason.trim())}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
};
