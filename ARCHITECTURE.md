# Architecture

The as-built system. Where a Phase 2 internal is already documented in depth, this file points there rather than restating it — see [`phase2/README.md`](phase2/README.md) for retrieval, evidence ranking, the confidence gate and the scope boundary.

---

## 1. Three stages, two databases, one enforced boundary

```
                    Public sources (allowlisted)
                              |
  ┌───────────────────────────┴───────────────────────────┐
  │ [1] data-ingestion-system/          Phase 1 · frozen  │
  │     8 async ingestors · httpx + tenacity              │
  │     APScheduler, fixed intervals                      │
  │     No AI code, by design                             │
  └───────────────────────────┬───────────────────────────┘
                              v
                   haemophilia_data.db
        raw_items · ingestor_logs · scheduling_metadata
                              |
  ┌───────────────────────────┴───────────────────────────┐
  │ [2] llm_1/                          Phase 1b          │
  │     deterministic rules layer, then LLM fallback      │
  │     writes -> classifications (same database)         │
  └───────────────────────────┬───────────────────────────┘
                              |
            ==== mode=ro · read-only · never written ====
                              v
  ┌───────────────────────────────────────────────────────┐
  │ [3] phase2/                         Phase 2           │
  │     chunk + embed + FTS5  ->  phase2/data/phase2.db   │
  │     hybrid retrieval -> evidence ranking              │
  │     confidence gate -> generation (or abstention)     │
  │     urgency scoring -> role routing -> signal cards   │
  │     FastAPI :8000  +  Next.js :3000                   │
  └───────────────────────────────────────────────────────┘
```

## 2. Why the boundary is a URI flag and not a convention

Phase 2 opens Phase 1's database as `file:...?mode=ro`. A stray `INSERT` raises `sqlite3.OperationalError` instead of silently mutating the corpus. Every Phase 2 write — chunks, embeddings, snapshots, change rows, chat threads, caches — lands in `phase2/data/phase2.db`.

Three things follow:

- Phase 1 can be re-ingested, migrated or replaced without coordinating with Phase 2.
- Deleting the sidecar resets all derived state and loses nothing original.
- A Phase 2 bug cannot corrupt the evidence base. In a system whose entire value proposition is provenance, that is not a nicety.

`classifications` is the one table Phase 2 reads live rather than indexing, so re-running the classifier is reflected immediately without an index rebuild.

## 3. Stage detail

### Ingestion — `data-ingestion-system/`

Eight ingestors behind one `BaseIngestor` contract (`app/ingestors/base.py`): each implements `fetch(last_cursor) -> (items, next_cursor)` and inherits retry, rate-limit handling, idempotent upsert and run logging. Cursors persist in `scheduling_metadata`, so a run resumes where the last one stopped.

Idempotency is on `(source_name, source_id)`. Re-running an ingestor never duplicates.

Scheduling is `AsyncIOScheduler` with fixed `IntervalTrigger`s and `max_instances=1` per job. There are no cron expressions and no date triggers — the consequence of which is [`docs/EXPECTATION_LEDGER.md`](docs/EXPECTATION_LEDGER.md).

### Classification — `llm_1/`

Two layers, in order:

1. **Rules** (`paper_validator.py:rules_layer`) — deterministic, auditable, free. Resolves what can be resolved from structured fields alone.
2. **LLM** (`llm_classifier.py`) — only for what the rules cannot reach. Structured JSON output, parsed and validated against a fixed category set; an unparseable reply is a recorded failure, never a guess. `classify_with_council` runs several models and requires a strict majority.

Four categories: `proven_right`, `proven_false`, `proven_false_but_useful`, `still_working_on`.

### Retrieval and intelligence — `phase2/`

Documented in full at [`phase2/README.md`](phase2/README.md). The short version, and the reasoning that matters:

- **Hybrid, not vector-only.** BM25 catches exact identifiers — `NCT06550882`, a PMID, a sponsor's legal name — that embeddings blur. Vectors catch paraphrase that BM25 misses. Fusion is Reciprocal Rank Fusion, which uses only ranks, so two incomparable score scales need no tuning.
- **Evidence ranking is a separate stage from search.** Search returns what matches; evidence ranking decides what is worth showing, applying bounded completeness and recency multipliers that break ties without overriding relevance.
- **The confidence gate runs before generation.** With insufficient evidence, no LLM call is made at all. Self-reported confidence can only be lowered afterwards, never raised.
- **The model never writes SQL.** Aggregates come from a whitelisted registry (`api/aggregates.py`); the model names a query. Tool round-trips are capped at exactly one.

## 4. Change detection

`item_snapshot` stores a content hash and extracted fields per item per observation. `item_change` records the transitions between consecutive snapshots. Three change kinds, weighted in `api/signals.py`:

| Kind | Weight | Meaning |
|---|---|---|
| `overall_status` | 1.50 | A trial changed status — the strongest signal available |
| `_field` | 1.25 | A tracked field moved |
| `record` | 1.00 | The record was first seen |

**Current state: every one of the 1,399 rows is at `record` — first seen.** The corpus was ingested in a single backfill and never re-run, so the diff engine is wired, exercised and correct, but has not yet had a second observation to diff against. This is a data-collection gap, not an implementation gap: a second ingestion run produces real transitions with no code change.

## 5. Urgency and routing

`urgency_for()` composes the same completeness and recency factors used in evidence ranking with the change weight and classifier verdict weight above. Reusing the functions is deliberate — a record cannot be judged urgent here and unimportant there.

Thresholds are calibrated against the corpus rather than guessed: with completeness capped at 1.00 and recency at 1.10, a never-changed record tops out at 1.07, so `HIGH_THRESHOLD = 1.02` keeps the high band reachable and non-empty. A trial that changes status clears it outright on the change weight alone.

## 6. API surface

18 endpoints on FastAPI (`phase2/api/main.py`), grouped:

| Group | Endpoints |
|---|---|
| Health / environment | `/api/health` |
| Feed and facets | `/api/feed`, `/api/facets`, `/api/landscape`, `/api/landscape/refresh` |
| Items | `/api/items/{id}`, `/api/items/{id}/summary`, `/api/items/{id}/similar` |
| Signals | `/api/signals`, `/api/signals/{id}`, `/api/signals/{id}/review` |
| Chat | `/api/chat/item/{id}`, `/api/chat/global`, `/api/threads/{id}` |
| Papers / categories | `/api/papers`, `/api/papers/{id}`, `/api/categories/{cat}` |
| Classification | `/api/classifications/recheck` |

Both chat endpoints stream over SSE with a withholding buffer, so a reply that fails post-generation validation is never partially shown and then retracted.
