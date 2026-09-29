/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { Select } from "@plane/blocks/select";
import { Input, InputGroup } from "@makeplane/propel/components/input";
// local imports
import type { TRelativeDateUnit } from "./relative-date";
import { RELATIVE_DATE_UNITS, buildRelativeDate, isRelativeDate, parseRelativeDate } from "./relative-date";

const I18N = "workspace_settings.settings.custom_fields.form";

type TDateMode = "fixed" | "relative";
const DATE_MODES: TDateMode[] = ["fixed", "relative"];

const NATIVE_INPUT_CLASS =
  "w-full rounded-md border border-strong bg-surface-1 px-2.5 py-1.5 text-body-sm-regular text-primary outline-none focus:border-accent-strong";

type Props = {
  value: string | number | undefined;
  onChange: (value: string | undefined) => void;
  /** datetime fields need a time component on the fixed-date input */
  variant?: "date" | "datetime";
};

/**
 * Picks either a fixed calendar date or a date relative to today ("today + 30 days"),
 * for a date field's earliest/latest bound. Relative bounds keep their meaning as
 * time passes, which fixed dates cannot.
 */
export function DateSettingInput(props: Props) {
  const { value, onChange, variant = "date" } = props;
  const { t } = useTranslation();

  const relative = parseRelativeDate(value);
  const isRelative = isRelativeDate(value);

  const unitLabel = (unit: TRelativeDateUnit) => t(`${I18N}.relative_unit.${unit}`);

  return (
    <div className="space-y-1.5">
      <Select<TDateMode>
        getValues={() => DATE_MODES}
        value={isRelative ? "relative" : "fixed"}
        onChange={(mode) => {
          // switching modes clears the old representation rather than trying to convert it
          onChange(mode === "relative" ? "today" : undefined);
        }}
        getOptionValue={(mode) => mode}
        getOptionLabel={(mode) => t(`${I18N}.${mode}`)}
        showSearch={false}
        pinSelected={false}
      >
        <Select.Trigger<TDateMode> variant="select-xl">
          {(selected) => <span className="truncate">{t(`${I18N}.${selected[0] ?? "fixed"}`)}</span>}
        </Select.Trigger>
      </Select>

      {isRelative ? (
        <div className="flex items-center gap-1.5">
          <span className="shrink-0 text-body-sm-regular text-tertiary">{t(`${I18N}.today`)}</span>
          <div className="w-20">
            <InputGroup size="xl">
              <Input
                size="xl"
                type="number"
                value={relative?.offset ?? 0}
                onChange={(e) => {
                  const offset = Number(e.target.value);
                  onChange(
                    buildRelativeDate({ offset: Number.isFinite(offset) ? offset : 0, unit: relative?.unit ?? "d" })
                  );
                }}
                aria-label={t(`${I18N}.relative_offset`)}
              />
            </InputGroup>
          </div>
          <Select<TRelativeDateUnit>
            getValues={() => RELATIVE_DATE_UNITS}
            value={relative?.unit ?? "d"}
            onChange={(unit) =>
              onChange(buildRelativeDate({ offset: relative?.offset ?? 0, unit: unit as TRelativeDateUnit }))
            }
            getOptionValue={(unit) => unit}
            getOptionLabel={unitLabel}
            showSearch={false}
            pinSelected={false}
          >
            <Select.Trigger<TRelativeDateUnit> variant="select-xl">
              {(selected) => <span className="truncate">{unitLabel(selected[0] ?? "d")}</span>}
            </Select.Trigger>
          </Select>
        </div>
      ) : (
        <input
          type={variant === "datetime" ? "datetime-local" : "date"}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value || undefined)}
          className={NATIVE_INPUT_CLASS}
        />
      )}
    </div>
  );
}
