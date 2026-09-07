"use client";

import { ALL_ROLES, ROLE_FOCUS } from "@/lib/roles";
import { useFacets } from "@/hooks/useSignals";
import { useRole } from "@/app/providers";

export function TopBar() {
  const { role, setRole } = useRole();
  const { data: facets } = useFacets();

  // A preset built on classifier verdicts is only offered once the classifier
  // has actually run. Offering one that can only ever return nothing would be
  // a broken promise, not an empty result.
  const roles = ALL_ROLES.filter(
    (name) =>
      ROLE_FOCUS[name].verdicts.length === 0 || facets?.classifications_available
  );

  return (
    <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border bg-surface px-6 py-3">
      <div className="min-w-0">
        <h1 className="text-sm font-semibold text-ink">Haemophilia Intelligence Radar</h1>
        <p className="truncate text-[11px] text-ink-muted">{ROLE_FOCUS[role].description}</p>
      </div>
      <label className="flex shrink-0 items-center gap-2 text-xs text-ink-muted">
        Viewing as
        <select
          value={role}
          onChange={(event) => setRole(event.target.value as typeof role)}
          className="rounded-md border border-border bg-paper px-2 py-1.5 text-xs text-ink focus-visible:outline-none"
        >
          {roles.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
    </header>
  );
}
