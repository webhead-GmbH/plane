/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { CSSProperties, KeyboardEvent, RefObject } from "react";
import { Combobox } from "@headlessui/react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { SearchOutline } from "@makeplane/propel/icons";
// plane web imports
import { StateOption } from "@/components/workflow";
import type { TStateOptionProps } from "@/components/workflow";

type TStateDropdownOptionsProps = {
  filteredOptions: TStateOptionProps["option"][] | undefined;
  inputRef: RefObject<HTMLInputElement | null>;
  popperAttributes: Record<string, string> | undefined;
  popperStyle: CSSProperties | undefined;
  query: string;
  searchInputKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  setPopperElement: (element: HTMLDivElement | null) => void;
  setQuery: (query: string) => void;
  stateOptionProps: Omit<TStateOptionProps, "option" | "selectedValue" | "className">;
  value: string | undefined | null;
};

/**
 * The search box and the list of states shown by the work item state and intake state dropdowns.
 */
export function StateDropdownOptions(props: TStateDropdownOptionsProps) {
  const {
    filteredOptions,
    inputRef,
    popperAttributes,
    popperStyle,
    query,
    searchInputKeyDown,
    setPopperElement,
    setQuery,
    stateOptionProps,
    value,
  } = props;
  // plane hooks
  const { t } = useTranslation();

  return (
    <Combobox.Options as="ul" className="fixed z-10" static modal={false}>
      <div
        className="my-1 w-48 rounded-sm border-[0.5px] border-strong bg-surface-1 px-2 py-2.5 text-11 shadow-raised-200 focus:outline-none"
        ref={setPopperElement}
        style={popperStyle}
        {...popperAttributes}
      >
        <div className="flex items-center gap-1.5 rounded-sm border border-subtle bg-surface-2 px-2">
          <SearchOutline className="h-3.5 w-3.5 text-placeholder" />
          <Combobox.Input
            as="input"
            ref={inputRef}
            className="w-full bg-transparent py-1 text-11 text-secondary placeholder:text-placeholder focus:outline-none"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("common.search.label")}
            displayValue={(assigned: any) => assigned?.name}
            onKeyDown={searchInputKeyDown}
          />
        </div>
        <div className="mt-2 max-h-48 space-y-1 overflow-y-scroll">
          {filteredOptions ? (
            filteredOptions.length > 0 ? (
              filteredOptions.map((option) => (
                <StateOption
                  {...stateOptionProps}
                  key={option.value}
                  option={option}
                  selectedValue={value}
                  className="flex w-full cursor-pointer items-center justify-between gap-2 truncate rounded-sm px-1 py-1.5 select-none"
                />
              ))
            ) : (
              <p className="px-1.5 py-1 text-placeholder italic">{t("no_matching_results")}</p>
            )
          ) : (
            <p className="px-1.5 py-1 text-placeholder italic">{t("loading")}</p>
          )}
        </div>
      </div>
    </Combobox.Options>
  );
}
