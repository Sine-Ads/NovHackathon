import type {
  Evidence,
  Facets,
  FeedItem,
  ItemDetail,
  LandscapeStats,
  Summary,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} for ${path}`);
  }
  return response.json() as Promise<T>;
}

export interface FeedQuery {
  q?: string;
  sources?: string[];
  statuses?: string[];
  categories?: string[];
  sort?: string;
  limit?: number;
  offset?: number;
}

export function fetchFeed(
  query: FeedQuery
): Promise<{ items: FeedItem[]; total: number; mode: string }> {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  (query.sources ?? []).forEach((s) => params.append("source", s));
  (query.statuses ?? []).forEach((s) => params.append("status", s));
  (query.categories ?? []).forEach((c) => params.append("category", c));
  if (query.sort) params.set("sort", query.sort);
  params.set("limit", String(query.limit ?? 30));
  params.set("offset", String(query.offset ?? 0));
  return get(`/api/feed?${params.toString()}`);
}

export const fetchFacets = () => get<Facets>("/api/facets");
export const fetchLandscape = () => get<LandscapeStats>("/api/landscape");
export const fetchItem = (id: string) =>
  get<ItemDetail>(`/api/items/${encodeURIComponent(id)}`);

export const fetchSimilar = (id: string, k = 6) =>
  get<{ similar: Evidence[] }>(
    `/api/items/${encodeURIComponent(id)}/similar?k=${k}`
  );

export async function fetchSummary(id: string): Promise<Summary> {
  const response = await fetch(
    `${API_BASE}/api/items/${encodeURIComponent(id)}/summary`,
    { method: "POST" }
  );
  if (!response.ok) throw new Error(`Summary failed: ${response.status}`);
  return response.json();
}

export interface StreamHandlers {
  onEvidence?: (evidence: Evidence[], route: string, facts: string | null) => void;
  onFacts?: (facts: string) => void;
  onDelta?: (text: string) => void;
  onDone?: (confidence: string, citations: string[]) => void;
  onError?: (message: string) => void;
}

/**
 * Consume an SSE stream from a POST endpoint.
 *
 * EventSource cannot be used here: it only issues GET requests and cannot carry
 * a JSON body, so the stream is read off fetch's ReadableStream directly.
 */
export async function streamChat(
  path: string,
  body: Record<string, unknown>,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    handlers.onError?.(
      `Could not reach the API at ${API_BASE}. Is the backend running on port 8000?`
    );
    return;
  }

  if (!response.ok || !response.body) {
    handlers.onError?.(`API returned ${response.status}`);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      let payload: any;
      try {
        payload = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      switch (payload.type) {
        case "evidence":
          handlers.onEvidence?.(
            payload.evidence ?? [],
            payload.route ?? "",
            payload.facts ?? null
          );
          break;
        case "facts":
          handlers.onFacts?.(payload.facts ?? "");
          break;
        case "delta":
          handlers.onDelta?.(payload.text ?? "");
          break;
        case "done":
          handlers.onDone?.(payload.confidence ?? "", payload.citations ?? []);
          break;
        case "error":
          handlers.onError?.(payload.message ?? "Unknown error");
          break;
      }
    }
  }
}

/** Format a source-defined date without implying a shared meaning. */
export function formatDate(value: string | null): string {
  if (!value) return "unknown";
  return value.slice(0, 10);
}
