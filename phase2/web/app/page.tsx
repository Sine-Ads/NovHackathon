"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchLandscape } from "@/lib/api";
import { userMessage } from "@/lib/errors";
import type { SignalFilters } from "@/lib/types";
import { ROLE_FOCUS } from "@/lib/roles";
import { PAGE_SIZE, useFacets, useSignals } from "@/hooks/useSignals";
import { useRole } from "./providers";
import { FilterRail } from "@/components/FilterRail";
import { GlobalChatDock } from "@/components/GlobalChatDock";
import { LandscapeStrip } from "@/components/LandscapeStrip";
import { SignalRow } from "@/components/SignalRow";

const EMPTY: SignalFilters = {
  q: "",
  urgency: [],
  kinds: [],
  indications: [],
  sources: [],
  verdicts: [],
  reviewed: "all",
  changedOnly: false,
  sort: "urgency",
};

const SORTS = [
  { value: "urgency", label: "Urgency" },
  { value: "detected", label: "Recently detected" },
  { value: "date", label: "Publication date" },
  { value: "title", label: "Title" },
  { value: "source", label: "Source" },
];

export default function RadarFeedPage() {
  const router = useRouter();
  const { role } = useRole();
  const [filters, setFilters] = useState<SignalFilters>(EMPTY);
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [page, setPage] = useState(0);

  // Only the search box is debounced — a checkbox should apply on the click.
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(filters.q), 300);
    return () => clearTimeout(handle);
  }, [filters.q]);

  const applied = useMemo(
    () => ({ ...filters, q: debouncedQuery }),
    [filters, debouncedQuery]
  );

  // A role is a preset, not a hidden filter: it writes into the same rail the
  // reader can see and change.
  useEffect(() => {
    const focus = ROLE_FOCUS[role];
    setFilters((current) => ({ ...current, kinds: focus.kinds, verdicts: focus.verdicts }));
    setPage(0);
  }, [role]);

  const { data: facets } = useFacets();
  const { data: stats } = useQuery({ queryKey: ["landscape"], queryFn: fetchLandscape });
  const { data, isPending, isFetching, error } = useSignals(applied, page);

  const change = useCallback((next: SignalFilters) => {
    setFilters(next);
    setPage(0);
  }, []);

  const pages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;
  const presetActive = ROLE_FOCUS[role].kinds.length > 0 || ROLE_FOCUS[role].verdicts.length > 0;

  return (
    <div className="flex h-full">
      <FilterRail facets={facets} filters={filters} onChange={change} />

      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="border-b border-border px-4 py-3">
          <LandscapeStrip stats={stats ?? null} />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-paper px-4 py-2">
          <span className="text-[11px] text-ink-muted">
            {error ? (
              <span className="text-high">{userMessage("feed", error)}</span>
            ) : isPending ? (
              "Loading signals…"
            ) : (
              <>
                {data?.total.toLocaleString()} signal{data?.total === 1 ? "" : "s"}
                {data?.mode === "relevance" ? " ranked by relevance" : ""}
                {presetActive ? ` · preset for ${role}` : ""}
                {isFetching ? " · updating" : ""}
              </>
            )}
          </span>

          <label className="flex items-center gap-2 text-[11px] text-ink-muted">
            Sort
            <select
              value={filters.sort}
              disabled={data?.mode === "relevance"}
              onChange={(event) => change({ ...filters, sort: event.target.value })}
              className="rounded-md border border-border bg-surface px-2 py-1 text-[11px] text-ink disabled:opacity-50 focus-visible:outline-none"
              title={
                data?.mode === "relevance"
                  ? "A search is ordered by how well each record matches; re-sorting it would misrepresent the ranking."
                  : undefined
              }
            >
              {SORTS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {filters.sort === "detected" && facets?.with_change_count === 0 && (
          <p className="border-b border-border px-4 py-2 text-[11px] leading-relaxed text-ink-muted">
            Every record was first seen in the same backfill run, so this
            ordering is the order that run inserted them — not a spread of
            detection dates. It becomes meaningful after a second ingestion.
          </p>
        )}

        {data?.items.map((signal) => (
          <SignalRow key={signal.id} signal={signal} />
        ))}

        {data && data.items.length === 0 && !error && (
          <p className="p-6 text-sm text-ink-muted">No signals match the current filters.</p>
        )}

        {pages > 1 && (
          <div className="flex items-center justify-center gap-3 p-4 text-xs">
            <button
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-ink disabled:opacity-40"
              disabled={page === 0}
              onClick={() => setPage((value) => value - 1)}
            >
              Previous
            </button>
            <span className="text-ink-muted">
              Page {page + 1} of {pages}
            </span>
            <button
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-ink disabled:opacity-40"
              disabled={page + 1 >= pages}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>

      <GlobalChatDock onOpenItem={(id) => router.push(`/signal/${encodeURIComponent(id)}`)} />
    </div>
  );
}
