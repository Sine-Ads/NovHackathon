"use client";

import type { ReactNode } from "react";
import type { Facets, SignalCategory, SignalFilters, Urgency } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Every group is driven by facet counts from the backend, so the rail offers
 * only values the corpus actually contains. An empty tier is never rendered as
 * a filter that returns nothing.
 */
function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

export function FilterRail({
  facets,
  filters,
  onChange,
}: {
  facets: Facets | undefined;
  filters: SignalFilters;
  onChange: (next: SignalFilters) => void;
}) {
  return (
    <aside className="w-60 shrink-0 space-y-6 overflow-y-auto border-r border-border p-4">
      <input
        type="search"
        placeholder="Search the corpus"
        value={filters.q}
        onChange={(event) => onChange({ ...filters, q: event.target.value })}
        className="w-full rounded-md border border-border bg-paper px-2.5 py-1.5 text-xs text-ink placeholder:text-ink-muted focus-visible:outline-none"
      />

      <Group label="Urgency">
        {(facets?.urgencies ?? []).map(({ name, count }) => (
          <Check
            key={name}
            label={name}
            count={count}
            checked={filters.urgency.includes(name as Urgency)}
            onChange={() => onChange({ ...filters, urgency: toggle(filters.urgency, name as Urgency) })}
          />
        ))}
      </Group>

      <Group label="Category">
        {(facets?.kinds ?? []).map(({ name, count }) => (
          <Check
            key={name}
            label={name}
            count={count}
            checked={filters.kinds.includes(name as SignalCategory)}
            onChange={() => onChange({ ...filters, kinds: toggle(filters.kinds, name as SignalCategory) })}
          />
        ))}
      </Group>

      <Group label="Indication">
        {(facets?.indications ?? []).map(({ name, count }) => (
          <Check
            key={name}
            label={name}
            count={count}
            checked={filters.indications.includes(name)}
            onChange={() => onChange({ ...filters, indications: toggle(filters.indications, name) })}
          />
        ))}
      </Group>

      <Group label="Source">
        {(facets?.sources ?? []).map(({ name, count }) => (
          <Check
            key={name}
            label={name}
            count={count}
            checked={filters.sources.includes(name)}
            onChange={() => onChange({ ...filters, sources: toggle(filters.sources, name) })}
          />
        ))}
      </Group>

      {facets?.classifications_available && facets.categories.length > 0 && (
        <Group label="Classifier verdict">
          {facets.categories.map(({ name, label, count }) => (
            <Check
              key={name}
              label={label}
              count={count}
              checked={filters.verdicts.includes(name)}
              onChange={() => onChange({ ...filters, verdicts: toggle(filters.verdicts, name) })}
            />
          ))}
        </Group>
      )}

      <Group label="Review status">
        {(["all", "unreviewed", "reviewed"] as const).map((value) => (
          <button
            key={value}
            onClick={() => onChange({ ...filters, reviewed: value })}
            className={cn(
              "block w-full rounded-md px-2 py-1 text-left text-xs capitalize",
              filters.reviewed === value
                ? "bg-accent-soft text-accent"
                : "text-ink-muted hover:bg-paper"
            )}
          >
            {value}
            {value === "reviewed" && facets ? ` (${facets.reviewed_count})` : ""}
          </button>
        ))}
      </Group>

      <Group label="Change">
        <Check
          label="Only records that moved"
          count={facets?.with_change_count}
          checked={filters.changedOnly}
          onChange={() => onChange({ ...filters, changedOnly: !filters.changedOnly })}
        />
        {facets?.with_change_count === 0 && (
          <p className="pt-1 text-[11px] leading-relaxed text-ink-muted">
            Nothing has been observed to change yet. Field-level diffs appear
            after a second ingestion run.
          </p>
        )}
      </Group>
    </aside>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <h4 className="mb-2 text-[11px] font-medium text-ink-muted">{label}</h4>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Check({
  label,
  count,
  checked,
  onChange,
}: {
  label: string;
  count?: number;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs text-ink">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="h-3.5 w-3.5 shrink-0 rounded-sm border-border accent-accent"
      />
      <span className="min-w-0 flex-1 truncate" title={label}>
        {label}
      </span>
      {count !== undefined && <span className="font-mono text-[10px] text-ink-muted">{count}</span>}
    </label>
  );
}
