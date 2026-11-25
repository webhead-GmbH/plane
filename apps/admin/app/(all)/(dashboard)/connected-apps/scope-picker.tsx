/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { Badge } from "@makeplane/propel/components/badge";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import type { TAgentScope } from "@plane/types";

type Props = {
  scopes: TAgentScope[];
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
};

/** What an app may ask people for, worded the way the person approving it will read it. */
export function ScopePicker(props: Props) {
  const { scopes, selected, onChange, disabled } = props;

  const chosen = new Set(selected);

  const toggle = (id: string, checked: boolean) =>
    onChange(checked ? [...selected.filter((scope) => scope !== id), id] : selected.filter((scope) => scope !== id));

  return (
    <fieldset className="space-y-2">
      <legend className="text-body-sm-medium text-primary">What the app may ask people for</legend>
      <p className="text-body-xs-regular text-tertiary">
        The app can ask for these and no more. Each person still decides, on a screen that lists what is asked, whether
        to connect it. Start with the least the app needs.
      </p>
      <ul className="divide-y divide-subtle rounded-lg border border-subtle">
        {scopes.map((scope) => (
          <li key={scope.id} className="space-y-1 px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Checkbox
                label={scope.title}
                checked={chosen.has(scope.id)}
                onCheckedChange={(checked) => toggle(scope.id, checked === true)}
                disabled={disabled}
              />
              {scope.writes && <Badge variant="warning" size="sm" label="Can make changes" />}
              {scope.others && <Badge variant="warning" size="sm" label="Sees other people's information" />}
            </div>
            <p className="ml-6 text-body-xs-regular text-tertiary">{scope.description}</p>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
