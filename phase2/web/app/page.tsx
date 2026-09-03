"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchFacets, fetchFeed, fetchLandscape } from "@/lib/api";
import type { Facets, FeedItem, LandscapeStats } from "@/lib/types";
import { FeedCard } from "@/components/FeedCard";
import { Filters, type FilterState } from "@/components/Filters";
import { GlobalChatDock } from "@/components/GlobalChatDock";
import { LandscapeStrip } from "@/components/LandscapeStrip";

const PAGE_SIZE = 25;

export default function Page() {
  const [facets, setFacets] = useState<Facets | null>(null);
  const [stats, setStats] = useState<LandscapeStats | null>(null);
  const [items, setItems] = useState<FeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [mode, setMode] = useState("browse");
  const [page, setPage] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    q: "",
    sources: [],
    statuses: [],
    categories: [],
    sort: "date",
  });

  useEffect(() => {
    fetchFacets().then(setFacets).catch(() => undefined);
    fetchLandscape().then(setStats).catch(() => undefined);
  }, []);

  useEffect(() => {
    // Debounced so typing in the search box does not fire a request per keystroke.
    const handle = setTimeout(() => {
      setLoading(true);
      setError(null);
      fetchFeed({
        q: filters.q || undefined,
        sources: filters.sources,
        statuses: filters.statuses,
        categories: filters.categories,
        sort: filters.sort,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
        .then((data) => {
          setItems(data.items);
          setTotal(data.total);
          setMode(data.mode);
        })
        .catch((e) =>
          setError(
            `Could not load the feed (${e}). Is the API running on port 8000?`
          )
        )
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [filters, page]);

  const changeFilters = useCallback((next: FilterState) => {
    setFilters(next);
    setPage(0);
    setOpenId(null);
  }, []);

  /** Open a record by id, pulling it into the feed if it is not on this page. */
  const openItem = useCallback(
    async (itemId: string) => {
      const present = items.some((i) => i.item_id === itemId);
      if (!present) {
        const data = await fetchFeed({ limit: 1, offset: 0 }).catch(() => null);
        if (data) {
          // Fall back to a direct lookup through search so the card can render.
          const found = await fetchFeed({ q: itemId, limit: 1 }).catch(() => null);
          if (found?.items.length) setItems((prev) => [found.items[0], ...prev]);
        }
      }
      setOpenId(itemId);
      setTimeout(
        () =>
          document
            .getElementById(`item-${itemId}`)
            ?.scrollIntoView({ behavior: "smooth", block: "center" }),
        80
      );
    },
    [items]
  );

  const pages = Math.ceil(total / PAGE_SIZE);

  return (
    <main className="shell">
      <header className="masthead">
        <h1>Haemophilia Intelligence Radar</h1>
        <p>
          Clinical trials, literature, preprints and corporate filings — searched
          together, with every answer showing what it stands on.
        </p>
      </header>

      <LandscapeStrip stats={stats} />
      <Filters facets={facets} state={filters} onChange={changeFilters} />

      {error && <p className="error">{error}</p>}
      {loading && <p className="spinner">Loading…</p>}

      {!loading && !error && (
        <p className="muted" style={{ fontSize: 12.5, marginTop: 0 }}>
          {total.toLocaleString()} record{total === 1 ? "" : "s"}
          {mode === "relevance" ? " ranked by relevance" : ""}
          {mode === "browse" && filters.sort === "date"
            ? " — dates mean different things by source, so each card says which it shows"
            : ""}
        </p>
      )}

      {!loading &&
        items.map((item) => (
          <FeedCard
            key={item.item_id}
            item={item}
            open={openId === item.item_id}
            onToggle={() =>
              setOpenId(openId === item.item_id ? null : item.item_id)
            }
            onOpenItem={openItem}
          />
        ))}

      {!loading && items.length === 0 && !error && (
        <p className="muted">No records match those filters.</p>
      )}

      {pages > 1 && (
        <div className="pager">
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            ← Previous
          </button>
          <span className="muted" style={{ alignSelf: "center" }}>
            Page {page + 1} of {pages}
          </span>
          <button
            disabled={page + 1 >= pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next →
          </button>
        </div>
      )}

      <GlobalChatDock onOpenItem={openItem} />
    </main>
  );
}
