"use client";

import type { Facets } from "@/lib/types";

export interface FilterState {
  q: string;
  sources: string[];
  statuses: string[];
  categories: string[];
  sort: string;
}

export function Filters({
  facets,
  state,
  onChange,
}: {
  facets: Facets | null;
  state: FilterState;
  onChange: (next: FilterState) => void;
}) {
  const toggle = (key: "sources" | "statuses" | "categories", value: string) => {
    const current = state[key];
    onChange({
      ...state,
      [key]: current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value],
    });
  };

  return (
    <div className="filters">
      <input
        type="search"
        value={state.q}
        placeholder="Search titles, abstracts, sponsors, conditions, NCT or PMID…"
        onChange={(e) => onChange({ ...state, q: e.target.value })}
      />

      <select
        value={state.sort}
        onChange={(e) => onChange({ ...state, sort: e.target.value })}
        // Relevance ordering is implicit whenever a query is present, so the
        // sort control only applies to browsing.
        disabled={Boolean(state.q)}
        title={state.q ? "Search results are ordered by relevance" : "Sort order"}
      >
        <option value="date">Newest first</option>
        <option value="date_asc">Oldest first</option>
        <option value="title">Title A–Z</option>
        <option value="source">By source</option>
      </select>

      {facets?.sources.map((s) => (
        <button
          key={s.name}
          className={`chip ${state.sources.includes(s.name) ? "on" : ""}`}
          onClick={() => toggle("sources", s.name)}
        >
          {s.name} {s.count}
        </button>
      ))}

      {/* Verdict chips appear only once the classifier has run — the
          classifications table arrives with alembic revision 002. */}
      {facets?.classifications_available &&
        facets.categories.map((c) => (
          <button
            key={c.name}
            className={`chip ${state.categories.includes(c.name) ? "on" : ""}`}
            onClick={() => toggle("categories", c.name)}
            title="Classifier verdict"
          >
            {c.label} {c.count}
          </button>
        ))}

      {facets?.classifications_available && facets.failed_count > 0 && (
        <button
          className={`chip ${state.categories.includes("failed") ? "on" : ""}`}
          onClick={() => toggle("categories", "failed")}
          title="Records the classifier could not process — unclassified, not disproven"
        >
          unclassified {facets.failed_count}
        </button>
      )}

      {facets?.trial_statuses.slice(0, 5).map((s) => (
        <button
          key={s.name}
          className={`chip ${state.statuses.includes(s.name) ? "on" : ""}`}
          onClick={() => toggle("statuses", s.name)}
        >
          {s.name.replace(/_/g, " ").toLowerCase()} {s.count}
        </button>
      ))}

      {(state.sources.length > 0 ||
        state.statuses.length > 0 ||
        state.categories.length > 0 ||
        state.q) && (
        <button
          className="chip"
          onClick={() =>
            onChange({ q: "", sources: [], statuses: [], categories: [], sort: state.sort })
          }
        >
          Clear
        </button>
      )}
    </div>
  );
}
