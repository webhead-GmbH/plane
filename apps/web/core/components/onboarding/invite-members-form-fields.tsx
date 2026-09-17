/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ChangeEvent } from "react";
import { useState } from "react";
import { observer } from "mobx-react";
import type {
  Control,
  FieldArrayWithId,
  FieldErrors,
  UseFieldArrayRemove,
  UseFormGetValues,
  UseFormSetValue,
  UseFormWatch,
} from "react-hook-form";
import { Controller } from "react-hook-form";
import { usePopper } from "react-popper";
// icons
import { AddOutline, ChevronDownOutline, CloseCircleOutline, TickOutline } from "@makeplane/propel/icons";
import { Listbox } from "@headlessui/react";
// plane imports
import { Field } from "@makeplane/propel/components/field";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import type { EUserPermissions } from "@plane/constants";
import { ROLE, ROLE_DETAILS } from "@plane/constants";
import { useTranslation } from "@plane/i18n";

type EmailRole = {
  email: string;
  role: EUserPermissions;
  role_active: boolean;
};

export type TInviteMembersFormValues = {
  emails: EmailRole[];
};

type TInviteMembersFormFieldsProps = {
  control: Control<TInviteMembersFormValues>;
  emailColumnClassName: string;
  errors: FieldErrors<TInviteMembersFormValues>;
  fields: FieldArrayWithId<TInviteMembersFormValues, "emails", "id">[];
  getValues: UseFormGetValues<TInviteMembersFormValues>;
  isInvitationDisabled: boolean;
  onAddField: () => void;
  remove: UseFieldArrayRemove;
  setIsInvitationDisabled: (value: boolean) => void;
  setValue: UseFormSetValue<TInviteMembersFormValues>;
  watch: UseFormWatch<TInviteMembersFormValues>;
};

type InviteMemberFormProps = Omit<TInviteMembersFormFieldsProps, "onAddField"> & {
  index: number;
  field: FieldArrayWithId<TInviteMembersFormValues, "emails", "id">;
};

const emailRegex = /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i;

const placeholderEmails = [
  "charlie.taylor@frstflt.com",
  "octave.chanute@frstflt.com",
  "george.spratt@frstflt.com",
  "frank.coffyn@frstflt.com",
  "amos.root@frstflt.com",
  "edward.deeds@frstflt.com",
  "charles.m.manly@frstflt.com",
  "glenn.curtiss@frstflt.com",
  "thomas.selfridge@frstflt.com",
  "albert.zahm@frstflt.com",
];
const InviteMemberInput = observer(function InviteMemberInput(props: InviteMemberFormProps) {
  const {
    control,
    emailColumnClassName,
    index,
    fields,
    remove,
    errors,
    isInvitationDisabled,
    setIsInvitationDisabled,
    setValue,
    getValues,
    watch,
  } = props;

  const [referenceElement, setReferenceElement] = useState<HTMLButtonElement | null>(null);
  const [popperElement, setPopperElement] = useState<HTMLDivElement | null>(null);

  const { t } = useTranslation();

  const email = watch(`emails.${index}.email`);

  const emailOnChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.value === "") {
      const validEmail = fields.map((_, i) => emailRegex.test(getValues(`emails.${i}.email`))).includes(true);
      if (validEmail) {
        setIsInvitationDisabled(false);
      } else {
        setIsInvitationDisabled(true);
      }

      if (getValues(`emails.${index}.role_active`)) {
        setValue(`emails.${index}.role_active`, false);
      }
    } else {
      if (!getValues(`emails.${index}.role_active`)) {
        setValue(`emails.${index}.role_active`, true);
      }
      if (isInvitationDisabled && emailRegex.test(event.target.value)) {
        setIsInvitationDisabled(false);
      } else if (!isInvitationDisabled && !emailRegex.test(event.target.value)) {
        setIsInvitationDisabled(true);
      }
    }
  };

  const { styles, attributes } = usePopper(referenceElement, popperElement, {
    placement: "bottom-end",
    modifiers: [
      {
        name: "preventOverflow",
        options: {
          padding: 12,
        },
      },
    ],
  });

  return (
    <div>
      <div className="group relative grid grid-cols-10 gap-4">
        <div className={emailColumnClassName}>
          <Controller
            control={control}
            name={`emails.${index}.email`}
            rules={{
              pattern: {
                value: emailRegex,
                message: "Invalid Email ID",
              },
            }}
            render={({ field: { value, onChange, ref } }) => (
              <Field name="input" invalid={Boolean(errors.emails?.[index]?.email)}>
                <InputGroup size="2xl">
                  <Input
                    size="2xl"
                    id={`emails.${index}.email`}
                    name={`emails.${index}.email`}
                    type="text"
                    value={value}
                    onChange={(event) => {
                      emailOnChange(event);
                      onChange(event);
                    }}
                    ref={ref}
                    placeholder={placeholderEmails[index % placeholderEmails.length]}
                    autoComplete="off"
                  />
                </InputGroup>
              </Field>
            )}
          />
        </div>
        <div className="col-span-4 mr-8">
          <Controller
            control={control}
            name={`emails.${index}.role`}
            rules={{ required: true }}
            render={({ field: { value, onChange } }) => (
              <Listbox
                as="div"
                value={value}
                onChange={(val) => {
                  onChange(val);
                  setValue(`emails.${index}.role_active`, true);
                }}
                className="w-full flex-shrink-0 text-left"
              >
                <Listbox.Button
                  type="button"
                  ref={setReferenceElement}
                  className="flex w-full items-center justify-between gap-1 rounded-md border-[0.5px] border-strong px-2.5 py-2 text-13"
                >
                  <span
                    className={`text-13 ${
                      !getValues(`emails.${index}.role_active`) ? "text-placeholder" : "text-primary"
                    } sm:text-13`}
                  >
                    {ROLE[value]}
                  </span>

                  <ChevronDownOutline
                    className={`size-3 ${
                      !getValues(`emails.${index}.role_active`) ? "text-placeholder" : "text-primary"
                    }`}
                  />
                </Listbox.Button>

                <Listbox.Options as="div">
                  <div
                    className="shadow-sm absolute z-10 mt-1 h-fit w-48 space-y-1 rounded-md border border-strong bg-surface-1 p-2 focus:outline-none sm:w-60"
                    ref={setPopperElement}
                    style={styles.popper}
                    {...attributes.popper}
                  >
                    {Object.entries(ROLE_DETAILS).map(([key, roleDetails]) => (
                      <Listbox.Option
                        as="div"
                        key={key}
                        value={parseInt(key)}
                        className={({ active, selected }) =>
                          `cursor-pointer truncate rounded-sm px-1 py-1.5 select-none ${
                            active || selected ? "bg-onboarding-background-400/40" : ""
                          } ${selected ? "text-primary" : "text-secondary"}`
                        }
                      >
                        {({ selected }) => (
                          <div className="flex items-center gap-2 p-1 text-wrap">
                            <div className="flex flex-col">
                              <div className="text-13 font-medium">{t(roleDetails.i18n_title)}</div>
                              <div className="flex text-11 text-tertiary">{t(roleDetails.i18n_description)}</div>
                            </div>
                            {selected && <TickOutline className="h-4 w-4 shrink-0" />}
                          </div>
                        )}
                      </Listbox.Option>
                    ))}
                  </div>
                </Listbox.Options>
              </Listbox>
            )}
          />
        </div>
        {fields.length > 1 && (
          <button
            type="button"
            className="absolute right-0 hidden place-items-center self-center rounded-sm group-hover:grid"
            onClick={() => remove(index)}
          >
            <CloseCircleOutline className="h-5 w-5 pl-0.5 text-placeholder" />
          </button>
        )}
      </div>
      {email && !emailRegex.test(email) && (
        <div className="mx-8 my-1">
          <span className="text-13">🤥</span>{" "}
          <span className="mt-1 text-11 text-danger-primary">That doesn{"'"}t look like an email address.</span>
        </div>
      )}
    </div>
  );
});

export function InviteMembersFormFields(props: TInviteMembersFormFieldsProps) {
  const {
    control,
    emailColumnClassName,
    errors,
    fields,
    getValues,
    isInvitationDisabled,
    onAddField,
    remove,
    setIsInvitationDisabled,
    setValue,
    watch,
  } = props;

  return (
    <div className="w-full py-4 text-13">
      <div className="group relative mx-8 grid grid-cols-10 gap-4 py-2">
        <div className="col-span-6 px-1 text-13 font-medium text-secondary">Email</div>
        <div className="col-span-4 px-1 text-13 font-medium text-secondary">Role</div>
      </div>
      <div className="mb-3 space-y-3 sm:space-y-4">
        {fields.map((field, index) => (
          <InviteMemberInput
            watch={watch}
            getValues={getValues}
            setValue={setValue}
            isInvitationDisabled={isInvitationDisabled}
            setIsInvitationDisabled={(value: boolean) => setIsInvitationDisabled(value)}
            control={control}
            emailColumnClassName={emailColumnClassName}
            errors={errors}
            field={field}
            fields={fields}
            index={index}
            remove={remove}
            key={field.id}
          />
        ))}
      </div>
      <button
        type="button"
        className="mx-8 flex items-center gap-1.5 bg-transparent text-13 font-medium text-accent-primary outline-accent-strong"
        onClick={onAddField}
      >
        <AddOutline className="h-4 w-4" />
        Add another
      </button>
    </div>
  );
}
