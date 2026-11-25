/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
// components
import { CopyField } from "@/components/common/copy-field";
// local
import type { TRevealed } from "./helpers";

type Props = {
  revealed: TRevealed | null;
  onClose: () => void;
};

/**
 * Shows values the administrator has to hand to the app. A client secret is shown here once and nowhere
 * else, so the dialog says so and asks before it is dismissed any way but the Done button.
 */
export function RevealDialog(props: Props) {
  const { revealed, onClose } = props;
  // The last thing shown stays on screen while the dialog fades out, and is dropped once it has: a secret
  // should not outlive the dialog in the page's memory.
  const [shown, setShown] = useState<TRevealed | null>(revealed);
  if (revealed && revealed !== shown) setShown(revealed);
  const view = revealed ?? shown;

  return (
    <Dialog
      open={revealed !== null}
      // A secret that cannot be shown again is not lost to a stray click or Escape: those ask first. The
      // Done button closes the dialog from our own handler, which is never asked about.
      discard={{
        when: revealed?.once === true,
        title: "Close without copying the secret?",
        description:
          "Plane cannot show this secret again. If it is lost, you have to replace it and give the app the new one.",
        discardLabel: "Close anyway",
        keepLabel: "Go back",
      }}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      onOpenChangeComplete={(open) => {
        if (!open) setShown(null);
      }}
    >
      <DialogContent size="md">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{view?.title}</DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            <div className="flex flex-col gap-4">
              <p className="text-body-sm-regular text-secondary">{view?.intro}</p>
              {view?.once && (
                <Banner
                  variant="warning"
                  placement="inline"
                  title="Copy the secret now"
                  description="Plane keeps only a fingerprint of it, so it cannot be shown again. If it is lost, replace it and give the app the new one."
                />
              )}
              {view?.fields.map((field) => (
                <CopyField key={field.label} label={field.label} url={field.value} description={field.description} />
              ))}
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button variant="primary" size="md" stretch="auto" onClick={onClose} label="Done" />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
