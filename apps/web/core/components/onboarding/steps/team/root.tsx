/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { useFieldArray, useForm } from "react-hook-form";
// plane imports
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { EOnboardingSteps } from "@plane/types";
import { Spinner } from "@plane/ui";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
// services
import { WorkspaceService } from "@/services/workspace.service";
// components
import type { TInviteMembersFormValues } from "@/components/onboarding/invite-members-form-fields";
import { InviteMembersFormFields } from "@/components/onboarding/invite-members-form-fields";
import { CommonOnboardingHeader } from "../common";

type Props = {
  handleStepChange: (step: EOnboardingSteps, skipInvites?: boolean) => void;
};

// services
const workspaceService = new WorkspaceService();

export const InviteTeamStep = observer(function InviteTeamStep(props: Props) {
  const { handleStepChange } = props;

  const [isInvitationDisabled, setIsInvitationDisabled] = useState(true);

  const { workspaces } = useWorkspace();
  const workspacesList = Object.values(workspaces ?? {});
  const workspace = workspacesList[0];

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
    await handleStepChange(EOnboardingSteps.INVITE_MEMBERS);
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
          type: TOAST_TYPE.SUCCESS,
          title: "Success!",
          message: "Invitations sent successfully.",
        });
        await nextStep();
      })
      .catch((err) => {
        setToast({
          type: TOAST_TYPE.ERROR,
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
    <form
      className="flex flex-col gap-10"
      onSubmit={handleSubmit(onSubmit)}
      onKeyDown={(e) => {
        if (e.code === "Enter") e.preventDefault();
      }}
    >
      <CommonOnboardingHeader
        title="Invite your teammates"
        description="Work in plane happens best with your team. Invite them now to use Plane to its potential."
      />
      <InviteMembersFormFields
        control={control}
        emailColumnClassName="col-span-6"
        errors={errors}
        fields={fields}
        getValues={getValues}
        isInvitationDisabled={isInvitationDisabled}
        onAddField={appendField}
        remove={remove}
        setIsInvitationDisabled={setIsInvitationDisabled}
        setValue={setValue}
        watch={watch}
      />
      <div className="mx-auto flex w-full flex-col items-center justify-center gap-4 px-8 sm:px-2">
        <Button
          variant="primary"
          type="submit"
          size="xl"
          className="w-full"
          disabled={isInvitationDisabled || !isValid || isSubmitting}
        >
          {isSubmitting ? <Spinner height="20px" width="20px" /> : "Continue"}
        </Button>
        <Button variant="ghost" size="xl" className="w-full" onClick={nextStep}>
          I’ll do it later
        </Button>
      </div>
    </form>
  );
});
