/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useId } from "react";
import type { FC } from "react";
// plane imports
import { Switch } from "@makeplane/propel/components/switch";
import { ECustomFieldType } from "@plane/types";
import type { TCustomField, TCustomFieldOption, TCustomFieldRawValue, TCustomFieldUrlValue } from "@plane/types";
import { Select } from "@plane/blocks/select";
import { Field } from "@makeplane/propel/components/field";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { TextArea, TextAreaGroup } from "@makeplane/propel/components/text-area";
import { cn } from "@plane/utils";
// local imports
import { resolveDateSetting } from "./relative-date";

type Props = {
  // display_name names the native inputs for screen readers; the field form's preview has none yet
  field: Pick<TCustomField, "field_type" | "settings"> & Partial<Pick<TCustomField, "display_name">>;
  value: TCustomFieldRawValue;
  onChange: (value: TCustomFieldRawValue) => void;
  disabled?: boolean;
  hasError?: boolean;
};

/** Normalise a hyperlink value to { url, text }, tolerating legacy plain-string values. */
export const getUrlValue = (value: TCustomFieldRawValue): TCustomFieldUrlValue => {
  if (typeof value === "string") return { url: value, text: "" };
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const v = value as TCustomFieldUrlValue;
    return { url: v.url ?? "", text: v.text ?? "" };
  }
  return { url: "", text: "" };
};

const NATIVE_INPUT_CLASS =
  "w-full rounded-md border border-strong bg-surface-1 px-2.5 py-1.5 text-body-sm-regular text-primary outline-none focus:border-accent-strong disabled:opacity-60";

function CustomFieldParagraphInput(props: Props) {
  const { field, value, onChange, disabled, hasError } = props;
  const placeholder = field.settings?.placeholder ?? "";

  return (
    <Field invalid={hasError}>
      <TextAreaGroup resize="none">
        <TextArea
          size="lg"
          surface="field"
          rows={3}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
        />
      </TextAreaGroup>
    </Field>
  );
}

function CustomFieldNumberInput(props: Props) {
  const { field, value, onChange, disabled, hasError } = props;
  const { settings } = field;
  const placeholder = settings?.placeholder ?? "";

  return (
    <Field invalid={hasError}>
      <InputGroup size="xl">
        <Input
          size="xl"
          type="number"
          value={value === null || value === undefined ? "" : (value as number)}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
          min={settings?.min as number | undefined}
          max={settings?.max as number | undefined}
          step={settings?.step}
          placeholder={placeholder}
          disabled={disabled}
        />
      </InputGroup>
    </Field>
  );
}

function CustomFieldBooleanInput(props: Props) {
  const { field, value, onChange, disabled } = props;
  const { settings } = field;

  return (
    <div className="flex items-center gap-2">
      <Switch size="sm" checked={Boolean(value)} onCheckedChange={(val) => onChange(val)} disabled={disabled} />
      {settings?.label && <span className="text-body-sm-regular text-secondary">{settings.label}</span>}
    </div>
  );
}

function CustomFieldSingleSelectInput(props: Props) {
  const { field, value, onChange, disabled, hasError } = props;
  const { settings } = field;
  const placeholder = settings?.placeholder ?? "";
  const options = settings?.options ?? [];

  return (
    <Select<TCustomFieldOption>
      getValues={() => options}
      value={options.find((option) => option.id === value) ?? null}
      onChange={(val) => onChange(val)}
      disabled={disabled}
      getOptionValue={(option) => option.id}
      getOptionLabel={(option) => option.label}
      getOptionIcon={(option) =>
        option.color ? <span className="size-2.5 rounded-full" style={{ backgroundColor: option.color }} /> : undefined
      }
      showSearch={options.length > 7}
      pinSelected={false}
      contentSizing="anchor"
    >
      <Select.Trigger<TCustomFieldOption>
        variant="select-xl"
        className={cn("w-full", { "border-danger-strong": hasError })}
      >
        {(selected) => (
          <span className={cn("min-w-0 grow truncate text-left", { "text-placeholder": !selected[0] })}>
            {selected[0]?.label ?? (placeholder || "Select")}
          </span>
        )}
      </Select.Trigger>
    </Select>
  );
}

function CustomFieldRadioInput(props: Props) {
  const { field, value, onChange, disabled } = props;
  const options = field.settings?.options ?? [];
  // one name per rendered field, so its buttons form a group (arrow keys move between them)
  const groupName = useId();

  return (
    <div className="flex flex-col gap-1.5">
      {options.map((option) => (
        <label key={option.id} className="flex cursor-pointer items-center gap-2 text-body-sm-regular text-primary">
          <input
            type="radio"
            name={groupName}
            checked={value === option.id}
            onChange={() => onChange(option.id)}
            disabled={disabled}
            className="accent-accent-strong"
          />
          {option.label}
        </label>
      ))}
    </div>
  );
}

function CustomFieldMultiSelectInput(props: Props) {
  const { field, value, onChange, disabled } = props;
  const options = field.settings?.options ?? [];
  const selected = Array.isArray(value) ? (value as string[]) : [];
  const selectedIds = new Set(selected);
  const toggle = (id: string) => onChange(selectedIds.has(id) ? selected.filter((s) => s !== id) : [...selected, id]);

  return (
    <div className="flex flex-col gap-1.5">
      {options.map((option) => (
        <label key={option.id} className="flex cursor-pointer items-center gap-2 text-body-sm-regular text-primary">
          <input
            type="checkbox"
            checked={selectedIds.has(option.id)}
            onChange={() => toggle(option.id)}
            disabled={disabled}
            className="accent-accent-strong"
          />
          {option.label}
        </label>
      ))}
    </div>
  );
}

// min/max may be a fixed date or a relative token ("today+30d"), resolved on every render
function CustomFieldDateInput(props: Props) {
  const { field, value, onChange, disabled, hasError } = props;
  const { settings } = field;

  return (
    <input
      type="date"
      aria-label={field.display_name}
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value || null)}
      min={resolveDateSetting(settings?.min, "date")}
      max={resolveDateSetting(settings?.max, "date")}
      disabled={disabled}
      className={cn(NATIVE_INPUT_CLASS, { "border-danger-strong": hasError })}
    />
  );
}

// the same fixed-or-relative min/max as the date input, resolved on every render
function CustomFieldDateTimeInput(props: Props) {
  const { field, value, onChange, disabled, hasError } = props;
  const { settings } = field;

  return (
    <input
      type="datetime-local"
      aria-label={field.display_name}
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value || null)}
      min={resolveDateSetting(settings?.min, "datetime")}
      max={resolveDateSetting(settings?.max, "datetime")}
      disabled={disabled}
      className={cn(NATIVE_INPUT_CLASS, { "border-danger-strong": hasError })}
    />
  );
}

function CustomFieldColorInput(props: Props) {
  const { field, value, onChange, disabled, hasError } = props;

  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        aria-label={field.display_name}
        value={(value as string) || "#3f76ff"}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="size-8 shrink-0 cursor-pointer rounded-md border border-strong bg-surface-1"
      />
      <div className="w-32">
        <Field invalid={hasError}>
          <InputGroup size="xl">
            <Input
              size="xl"
              type="text"
              value={(value as string) ?? ""}
              onChange={(e) => onChange(e.target.value)}
              placeholder="#3f76ff"
              disabled={disabled}
            />
          </InputGroup>
        </Field>
      </div>
    </div>
  );
}

function CustomFieldUrlInput(props: Props) {
  const { field, value, onChange, disabled, hasError } = props;
  const placeholder = field.settings?.placeholder ?? "";
  const { url, text } = getUrlValue(value);

  return (
    <div className="w-full space-y-1.5">
      <Field invalid={hasError}>
        <InputGroup size="xl">
          <Input
            size="xl"
            type="url"
            value={url}
            onChange={(e) => onChange({ url: e.target.value, text })}
            placeholder={placeholder || "https://example.com"}
            disabled={disabled}
          />
        </InputGroup>
      </Field>
      <InputGroup size="xl">
        <Input
          size="xl"
          type="text"
          value={text}
          onChange={(e) => onChange({ url, text: e.target.value })}
          placeholder="Display text (optional)"
          disabled={disabled}
        />
      </InputGroup>
    </div>
  );
}

function CustomFieldTextInput(props: Props) {
  const { field, value, onChange, disabled, hasError } = props;
  const { field_type, settings } = field;
  const placeholder = settings?.placeholder ?? "";

  return (
    <Field invalid={hasError}>
      <InputGroup size="xl">
        <Input
          size="xl"
          type={field_type === ECustomFieldType.EMAIL ? "email" : "text"}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
        />
      </InputGroup>
    </Field>
  );
}

/** The editor for each field type; a type this build does not know falls back to plain text. */
const CUSTOM_FIELD_INPUTS: Record<ECustomFieldType, FC<Props>> = {
  [ECustomFieldType.PARAGRAPH]: CustomFieldParagraphInput,
  [ECustomFieldType.NUMBER]: CustomFieldNumberInput,
  [ECustomFieldType.BOOLEAN]: CustomFieldBooleanInput,
  [ECustomFieldType.SINGLE_SELECT]: CustomFieldSingleSelectInput,
  [ECustomFieldType.RADIO]: CustomFieldRadioInput,
  [ECustomFieldType.MULTI_SELECT]: CustomFieldMultiSelectInput,
  [ECustomFieldType.DATE]: CustomFieldDateInput,
  [ECustomFieldType.DATETIME]: CustomFieldDateTimeInput,
  [ECustomFieldType.COLOR]: CustomFieldColorInput,
  [ECustomFieldType.URL]: CustomFieldUrlInput,
  [ECustomFieldType.EMAIL]: CustomFieldTextInput,
  [ECustomFieldType.TEXT]: CustomFieldTextInput,
};

export function CustomFieldInput(props: Props) {
  const { field } = props;
  // hasOwn, so a type named like an Object.prototype member cannot pick up an inherited value
  const FieldInput = Object.hasOwn(CUSTOM_FIELD_INPUTS, field.field_type)
    ? CUSTOM_FIELD_INPUTS[field.field_type]
    : CustomFieldTextInput;

  return <FieldInput {...props} />;
}
