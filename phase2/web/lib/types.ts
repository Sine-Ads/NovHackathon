export type Confidence = "supported" | "inferred" | "insufficient";

/** Verdicts from Phase 1's classifier. Null category means the attempt failed. */
export type Category =
  | "proven_right"
  | "proven_false"
  | "proven_false_but_useful"
  | "still_working_on";

export interface Classification {
  category: Category | null;
  category_label: string | null;
  justification: string | null;
  method: "rule" | "llm" | null;
  status: "classified" | "failed";
  reason: string | null;
  classified_at: string | null;
}
export type SummaryConfidence = "high" | "medium" | "abstain";

export interface FeedItem {
  item_id: string;
  source_name: string;
  source_id: string;
  source_url: string | null;
  title: string | null;
  date_published: string | null;
  date_ingested: string;
  date_class: string;
  /** Source-specific label: "Study start" / "Published" / "Filed". */
  date_label: string;
  is_thin: boolean;
  n_chars: number;
  snippet: string;
  status: string | null;
  sponsor: string | null;
  journal: string | null;
  openfda_type: string | null;
  match_reason?: string;
  score?: number;
  classification?: Classification | null;
}

export interface Evidence {
  chunk_id: string;
  item_id: string;
  source_name: string;
  source_id: string;
  source_url: string | null;
  title: string | null;
  date_published: string | null;
  date_class: string;
  date_label: string;
  matched_by: string[];
  fts_rank: number | null;
  vec_rank: number | null;
  vec_score: number | null;
  rrf_score: number;
  evidence_score: number;
  completeness: number;
  recency: number;
  n_chars: number;
  is_thin: boolean;
  /** Deterministically generated — never written by the model. */
  reason: string;
  classification?: Classification | null;
}

export interface Summary {
  item_id: string;
  summary: string | null;
  why_matters: string | null;
  key_facts: string[];
  functions: string[];
  confidence: SummaryConfidence;
  cached: boolean;
  error?: string;
  provenance: {
    source_name: string;
    source_id: string;
    source_url: string | null;
    date_published: string | null;
    date_class: string;
  };
}

export interface ItemDetail extends Omit<FeedItem, "snippet" | "status" | "sponsor" | "journal" | "openfda_type"> {
  raw_content: string | null;
  metadata: Record<string, unknown>;
  classification?: Classification | null;
}

export interface Facets {
  sources: { name: string; count: number }[];
  trial_statuses: { name: string; count: number }[];
  categories: { name: Category; label: string; count: number }[];
  classifications_available: boolean;
  failed_count: number;
}

export interface LandscapeStats {
  total_items: number;
  by_source: Record<string, number>;
  trial_status: Record<string, number>;
  top_sponsors: [string, number][];
  top_conditions: [string, number][];
  undated_items: number;
  thin_items: number;
  caveats: string[];
  classifications?: {
    available: boolean;
    classified: number;
    failed: number;
    unclassified: number;
    corpus?: number;
    by_category: Record<string, number>;
    by_method: Record<string, number>;
  };
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  confidence?: Confidence | null;
  evidence?: Evidence[];
  facts?: string | null;
  route?: string;
  pending?: boolean;
}
