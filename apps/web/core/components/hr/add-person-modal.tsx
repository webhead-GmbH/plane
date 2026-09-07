/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Check, Search } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { EModalPosition, EModalWidth, ModalCore, Tooltip } from "@plane/ui";
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
  const [hireDate, setHireDate] = useState(() => new Date().toISOString().slice(0, 10));

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
          <h3 className="text-16 font-medium text-primary">{t("hr.people.add_title")}</h3>
          <p className="text-13 text-tertiary">{t("hr.people.add_hint")}</p>
        </div>

        <div className="flex items-center gap-2 rounded-md border border-subtle px-3 focus-within:border-accent-strong">
          <Search className="size-4 text-tertiary" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("hr.people.search_placeholder")}
            className="w-full bg-transparent py-2 text-13 text-primary outline-none"
          />
        </div>

        <div className="max-h-64 overflow-y-auto rounded-md border border-subtle">
          {shown.length === 0 ? (
            <EmptyStateCompact
              assetKey={candidates.length === 0 ? "work-item" : "search"}
              assetClassName="size-20"
              rootClassName="py-8"
              title={candidates.length === 0 ? t("hr.people.everybody_added") : t("hr.people.nobody_matches")}
              description={
                candidates.length === 0 ? t("hr.people.everybody_added_detail") : t("hr.people.nobody_matches_detail")
              }
            />
          ) : (
            shown.map((person) => (
              <button
                key={person.id}
                type="button"
                onClick={() => setChosen(person.id)}
                aria-pressed={chosen === person.id}
                className={cn(
                  "flex w-full items-center gap-3 border-b border-subtle px-3 py-2 text-left last:border-b-0",
                  chosen === person.id ? "bg-accent-primary/10" : "hover:bg-layer-1"
                )}
              >
                <span className="flex size-7 items-center justify-center rounded-full bg-layer-2 text-13 font-medium text-secondary uppercase">
                  {(person.display_name || person.email).charAt(0)}
                </span>
                <span className="flex flex-col">
                  <span className="text-13 text-primary">{person.display_name || person.email}</span>
                  {person.display_name ? <span className="text-13 text-tertiary">{person.email}</span> : null}
                </span>
                {/* Colour alone did not say which row was picked. */}
                {chosen === person.id ? <Check className="ml-auto size-4 text-accent-primary" /> : null}
              </button>
            ))
          )}
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-13 font-medium text-tertiary">{t("hr.people.hire_date")}</span>
          <input
            type="date"
            value={hireDate}
            onChange={(e) => setHireDate(e.target.value)}
            className="rounded-md border border-subtle bg-layer-1 px-3 py-1.5 text-13 text-primary outline-none focus:border-accent-strong"
          />
        </label>

        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("hr.people.cancel")}
          </Button>
          <Tooltip
            tooltipContent={chosen ? t("hr.people.pick_date_first") : t("hr.people.pick_somebody_first")}
            disabled={Boolean(chosen && hireDate)}
            position="top"
          >
            {/* A wrapper: a disabled button takes no pointer events of its own,
                so without this the reason never reaches the person stuck on it. */}
            <span>
              <Button
                variant="primary"
                size="lg"
                disabled={!chosen || !hireDate || isBusy}
                loading={isBusy}
                onClick={() => chosen && onAdd(chosen, hireDate)}
              >
                {t("hr.people.add_confirm")}
              </Button>
            </span>
          </Tooltip>
        </div>
      </div>
    </ModalCore>
  );
};
