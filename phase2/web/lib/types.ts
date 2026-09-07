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
  /** Present only where the endpoint returns the excerpt itself. */
  text?: string;
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

export interface Facets extends DerivedFacets {
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

// ---------------------------------------------------------------------------
// Signals — the same corpus seen as events rather than documents.
//
// Every field here is derived server-side from stored data. Fields the radar
// design carried that this corpus cannot support (geography, modality, review
// routing) are absent rather than optional: there is no value to hold.
// ---------------------------------------------------------------------------

export type Urgency = "HIGH" | "MEDIUM" | "LOW";

/** Derived from the source that supplied the record. */
export type SignalCategory = "Trial" | "Publication" | "Corporate" | "Other";

export interface ScoreFeature {
  feature: string;
  weight: number;
  direction: "up" | "down" | "neutral";
}

export interface SignalChange {
  field: string;
  field_label: string;
  before: string | null;
  after: string | null;
  detected_at: string;
  is_first_seen: boolean;
}

export interface Signal {
  id: string;
  /** Same value as `id`; lets record-level components take a signal unchanged. */
  item_id: string;
  title: string | null;
  category: SignalCategory;
  /** Null when the record names neither haemophilia A nor B. */
  indication: string | null;
  urgency: Urgency;
  score: number;
  score_breakdown: ScoreFeature[];
  /** Null until a watched field has been observed to move. */
  what_changed: SignalChange | null;
  detected_date: string;
  detected_label: string;
  change_count: number;
  reviewed: boolean;
  classification?: Classification | null;

  source_name: string;
  source_id: string;
  source_url: string | null;
  date_published: string | null;
  date_class: string;
  date_label: string;
  is_thin: boolean;
  n_chars: number;
  snippet: string;
  status: string | null;
  sponsor: string | null;
  journal: string | null;
  match_reason?: string;
}

export interface SignalDetail extends Signal {
  changes: SignalChange[];
  evidence: Evidence[];
}

export const INDICATION_UNSTATED = "Indication unstated";

export interface SignalFilters {
  q: string;
  urgency: Urgency[];
  kinds: SignalCategory[];
  indications: string[];
  sources: string[];
  verdicts: Category[];
  reviewed: "all" | "reviewed" | "unreviewed";
  changedOnly: boolean;
  sort: string;
}

export interface DerivedFacets {
  kinds: { name: SignalCategory; count: number }[];
  urgencies: { name: Urgency; count: number }[];
  indications: { name: string; count: number }[];
  reviewed_count: number;
  unreviewed_count: number;
  with_change_count: number;
}
