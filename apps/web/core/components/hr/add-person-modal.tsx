/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
import { cn } from "@plane/utils";
// services
import type { THrCandidate } from "@/services/hr.service";

type TProps = {
  isOpen: boolean;
  candidates: THrCandidate[];
  isBusy: boolean;
  onClose: () => void;
  onAdd: (memberId: string, hireDate: string) => void;
};

/**
 * Giving somebody an employment record.
 *
 * The list is of people already in the installation rather than a free-text
 * invitation, because an employment record has to point at the account whose
 * hours it will count. Somebody typed in by name would produce a person with a
 * month and no way to fill it.
 */
export const HrAddPersonModal = ({ isOpen, candidates, isBusy, onClose, onAdd }: TProps) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  const [hireDate, setHireDate] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    setQuery("");
    setChosen(null);
    setHireDate(new Date().toISOString().slice(0, 10));
  }, [isOpen]);

  const needle = query.trim().toLowerCase();
  const shown = needle
    ? candidates.filter(
        (person) => person.display_name.toLowerCase().includes(needle) || person.email.toLowerCase().includes(needle)
      )
    : candidates;

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXL}>
      <div className="flex flex-col gap-4 p-5">
        <div>
          <h3 className="text-custom-text-100 text-lg font-medium">{t("hr.people.add_title")}</h3>
          <p className="text-custom-text-300 text-sm">{t("hr.people.add_hint")}</p>
        </div>

        <div className="border-custom-border-200 focus-within:border-custom-primary-100 flex items-center gap-2 rounded-md border px-3">
          <Search className="text-custom-text-400 size-4" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("hr.people.search_placeholder")}
            className="text-custom-text-100 text-sm w-full bg-transparent py-2 outline-none"
          />
        </div>

        <div className="border-custom-border-200 max-h-64 overflow-y-auto rounded-md border">
          {shown.length === 0 ? (
            <p className="text-custom-text-300 text-sm px-3 py-6 text-center">
              {candidates.length === 0 ? t("hr.people.everybody_added") : t("hr.people.nobody_matches")}
            </p>
          ) : (
            shown.map((person) => (
              <button
                key={person.id}
                type="button"
                onClick={() => setChosen(person.id)}
                className={cn(
                  "border-custom-border-100 flex w-full items-center gap-3 border-b px-3 py-2 text-left last:border-b-0",
                  chosen === person.id ? "bg-custom-primary-100/10" : "hover:bg-custom-background-90"
                )}
              >
                <span className="bg-custom-background-80 text-custom-text-200 text-xs flex size-7 items-center justify-center rounded-full font-medium uppercase">
                  {(person.display_name || person.email).charAt(0)}
                </span>
                <span className="flex flex-col">
                  <span className="text-custom-text-100 text-sm">{person.display_name || person.email}</span>
                  {person.display_name ? <span className="text-custom-text-400 text-xs">{person.email}</span> : null}
                </span>
              </button>
            ))
          )}
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-custom-text-300 text-xs font-medium">{t("hr.people.hire_date")}</span>
          <input
            type="date"
            value={hireDate}
            onChange={(e) => setHireDate(e.target.value)}
            className="border-custom-border-200 bg-custom-background-100 text-custom-text-100 focus:border-custom-primary-100 text-sm rounded-md border px-3 py-1.5 outline-none"
          />
        </label>

        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("hr.people.cancel")}
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!chosen || !hireDate || isBusy}
            loading={isBusy}
            onClick={() => chosen && onAdd(chosen, hireDate)}
          >
            {t("hr.people.add_confirm")}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
};
