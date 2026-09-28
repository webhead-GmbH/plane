/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
// icons
// plane imports
// types
import { Button } from "@makeplane/propel/components/button";
import { Button as ButtonElement } from "@makeplane/propel/elements/button";
import { setToast } from "@plane/blocks/toast";
import type { IUser, IWorkspace } from "@plane/types";
// ui
import { Spinner } from "@plane/blocks/spinner";
import type { TInviteMembersFormValues } from "@/components/onboarding/invite-members-form-fields";
import { InviteMembersFormFields } from "@/components/onboarding/invite-members-form-fields";
// services
import { WorkspaceService } from "@/services/workspace.service";
// components
import { SwitchAccountDropdown } from "./switch-account-dropdown";

type Props = {
  finishOnboarding: () => Promise<void>;
  totalSteps: number;
  user: IUser | undefined;
  workspace: IWorkspace | undefined;
};

// services
const workspaceService = new WorkspaceService();

export function InviteMembers(props: Props) {
  const { finishOnboarding, workspace } = props;

  const [isInvitationDisabled, setIsInvitationDisabled] = useState(true);

  const {
    control,
    watch,
    getValues,
    setValue,
    handleSubmit,
    formState: { isSubmitting, errors, isValid },
  } = useForm<TInviteMembersFormValues>();

  const { fields, append, remove } = useFieldArray({
    control,
    name: "emails",
  });

  const nextStep = async () => {
    await finishOnboarding();
  };

  const onSubmit = async (formData: TInviteMembersFormValues) => {
    if (!workspace) return;

    let payload = { ...formData };
    payload = { emails: payload.emails.filter((email) => email.email !== "") };

    await workspaceService
      .inviteWorkspace(workspace.slug, {
        emails: payload.emails.map((email) => ({
          email: email.email,
          role: email.role,
        })),
      })
      .then(async () => {
        setToast({
          type: "success",
          title: "Success!",
          message: "Invitations sent successfully.",
        });
        await nextStep();
      })
      .catch((err) => {
        setToast({
          type: "error",
          title: "Error!",
          message: err?.error,
        });
      });
  };

  const appendField = () => {
    append({ email: "", role: 15, role_active: false });
  };

  useEffect(() => {
    if (fields.length === 0) {
      append(
        [
          { email: "", role: 15, role_active: false },
          { email: "", role: 15, role_active: false },
          { email: "", role: 15, role_active: false },
        ],
        {
          focusIndex: 0,
        }
      );
    }
  }, [fields, append]);

  return (
    <div className="flex h-full w-full">
      <div className="h-full w-full overflow-auto px-6 py-10 sm:px-7 sm:py-14 md:px-14 lg:px-28">
        <div className="mx-auto mt-6 flex w-full flex-col items-center justify-center p-8 md:w-4/5">
          <div className="mx-auto w-4/5 space-y-1 py-4 text-center">
            <h3 className="text-24 font-bold text-primary">Invite your teammates</h3>
            <p className="font-medium text-placeholder">
              Work in plane happens best with your team. Invite them now to use Plane to its potential.
            </p>
          </div>
          <form
            className="mx-auto mt-2 w-full space-y-4"
            onSubmit={handleSubmit(onSubmit)}
            onKeyDown={(e) => {
              if (e.code === "Enter") e.preventDefault();
            }}
          >
            <InviteMembersFormFields
              watch={watch}
              getValues={getValues}
              setValue={setValue}
              isInvitationDisabled={isInvitationDisabled}
              setIsInvitationDisabled={setIsInvitationDisabled}
              control={control}
              emailColumnClassName="col-span-6 ml-8"
              errors={errors}
              fields={fields}
              remove={remove}
              onAddField={appendField}
            />
            <div className="mx-auto flex w-full max-w-96 flex-col items-center justify-center gap-4 px-8 sm:px-2">
              <ButtonElement
                variant="primary"
                type="submit"
                size="lg"
                stretch="full"
                disabled={isInvitationDisabled || !isValid || isSubmitting}
              >
                {isSubmitting ? <Spinner height="20px" width="20px" /> : "Continue"}
              </ButtonElement>
              <Button variant="ghost" size="lg" stretch="full" onClick={nextStep} label="I’ll do it later" />
            </div>
          </form>
        </div>
      </div>
      <SwitchAccountDropdown />
    </div>
  );
}
