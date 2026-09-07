"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFacets, fetchSignal, fetchSignals, setReviewed } from "@/lib/api";
import type { SignalFilters } from "@/lib/types";

export const PAGE_SIZE = 25;

/**
 * One cache entry per (filters, page). The left rail and the feed both read the
 * corpus, and react-query is what stops that being two requests for the same
 * rows on every render.
 */
export function useSignals(filters: SignalFilters, page: number) {
  return useQuery({
    queryKey: ["signals", filters, page],
    queryFn: () => fetchSignals(filters, PAGE_SIZE, page * PAGE_SIZE),
    // Keep the previous page on screen while the next one loads, so paging and
    // typing in the search box do not blank the feed.
    placeholderData: keepPreviousData,
  });
}

export function useSignal(id: string) {
  return useQuery({
    queryKey: ["signal", id],
    queryFn: () => fetchSignal(id),
    enabled: Boolean(id),
  });
}

export function useFacets() {
  return useQuery({ queryKey: ["facets"], queryFn: fetchFacets });
}

/** Everything urgent that nobody has looked at yet — the left-rail badge. */
export function useUnreviewedHighCount() {
  const { data } = useQuery({
    queryKey: ["signals", "high-unreviewed"],
    queryFn: () =>
      fetchSignals(
        {
          q: "",
          urgency: ["HIGH"],
          kinds: [],
          indications: [],
          sources: [],
          verdicts: [],
          reviewed: "unreviewed",
          changedOnly: false,
          sort: "urgency",
        },
        1,
        0
      ),
  });
  return data?.total ?? 0;
}

export function useReviewToggle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reviewed }: { id: string; reviewed?: boolean }) =>
      setReviewed(id, reviewed),
    onSuccess: (_data, variables) => {
      client.invalidateQueries({ queryKey: ["signals"] });
      client.invalidateQueries({ queryKey: ["signal", variables.id] });
      client.invalidateQueries({ queryKey: ["facets"] });
    },
  });
}
