/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { useFieldArray, useForm } from "react-hook-form";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Button as ButtonElement } from "@makeplane/propel/elements/button";
import { setToast } from "@plane/blocks/toast";
import { EOnboardingSteps } from "@plane/types";
import { Spinner } from "@plane/blocks/spinner";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
import type { TInviteMembersFormValues } from "@/components/onboarding/invite-members-form-fields";
import { InviteMembersFormFields } from "@/components/onboarding/invite-members-form-fields";
// services
import { WorkspaceService } from "@/services/workspace.service";
// components
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
        watch={watch}
        getValues={getValues}
        setValue={setValue}
        isInvitationDisabled={isInvitationDisabled}
        setIsInvitationDisabled={setIsInvitationDisabled}
        control={control}
        emailColumnClassName="col-span-6"
        errors={errors}
        fields={fields}
        remove={remove}
        onAddField={appendField}
      />
      <div className="mx-auto flex w-full flex-col items-center justify-center gap-4 px-8 sm:px-2">
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
  );
});
