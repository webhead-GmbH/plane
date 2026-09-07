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
          <span className="flex size-9 flex-shrink-0 items-center justify-center rounded-full bg-warning-subtle">
            <AlertTriangle className="size-4 text-warning-primary" />
          </span>
          <div className="flex flex-col gap-1">
            <h3 className="text-16 font-medium text-primary">{title}</h3>
            <p className="text-13 text-tertiary">{body}</p>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="hr-reason" className="text-13 font-medium text-secondary">
            {label}
          </label>
          <textarea
            id="hr-reason"
            ref={field}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            placeholder={placeholder}
            className="w-full resize-none rounded-md border border-subtle bg-layer-1 px-3 py-2 text-13 text-primary outline-none placeholder:text-tertiary focus:border-accent-strong"
          />
        </div>

        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button
            variant="primary"
            size="lg"
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
