# Limitations

What this system does not do, stated plainly. Everything here is a known, measured gap — not a caveat discovered under questioning.

---

## Data collection

**Four of eight connectors returned no records.** All eight are implemented and tested against mocked responses; four returned nothing against live endpoints.

| Connector | Result | Reason |
|---|---|---|
| OpenFDA | 0 | Adverse-event and enforcement endpoints returned no haemophilia matches for the query as issued |
| WHO ICTRP | 0 | The `Export.aspx` endpoint blocks automated access |
| medRxiv | 0 | No matching records in the queried window |
| USPTO | 0 | Requires `USPTO_API_KEY`, which we do not hold |

The consequence is stated in code rather than hidden: `phase2/api/signals.py` hard-codes the category map to the four sources that actually returned data, and the facets endpoint reports only categories genuinely present. **The Regulatory, HTA, Congress, Safety and Silence categories described in the concept note have no source behind them in this build and are never emitted.** They are not rendered as empty tabs.

**The corpus is a single backfill.** Everything was ingested on 2026-09-01 and the scheduler has not been run since. Two consequences:

- Every one of the 1,399 rows sits at change kind `record` — first seen. The diff engine is wired and correct but has not yet had a second observation to diff against. A second ingestion run produces real transitions with no code change.
- Nothing in the corpus is fresher than that date.

## Classification

- **`retracted`, `citation_count` and `publication_type` are collected by no ingestor.** The rules layer branches that depend on them are dead by construction, and the LLM receives `retracted=False`, `citation_count=0`, `publication_type="unknown"` for every record regardless of truth. Adding a Crossref or OpenAlex enrichment step would fix this; it is not in this build.
- **Only trial-status rules can fire.** They resolve 161 of 1,399 records: 90 `RECRUITING` → `still_working_on`, 71 `TERMINATED` → `proven_false`.
- **`WITHDRAWN`, `SUSPENDED`, `NOT_YET_RECRUITING` and `ACTIVE_NOT_RECRUITING` are unmapped** and fall through to the LLM. Mapping them is a judgement about clinical semantics we did not want to make unilaterally.
- The four categories are a coarse frame for a corpus that contains SEC filings and mathematical preprints alongside clinical papers. `still_working_on` is doing a lot of work.

## Retrieval and generation

- **Tool round-trips are capped at exactly one** (`phase2/api/chat.py:234`). A question needing two chained aggregates cannot be answered, by design — the cap prevents runaway loops at the cost of multi-hop questions.
- **Retrieval reruns from scratch every turn.** A fact seen in turn 2 is unavailable in turn 5 unless turn 5 retrieves it again. This prevents stale context masquerading as current retrieval, and it makes some follow-up phrasings fail.
- **Embeddings are `bge-small-en-v1.5`, 384-dim, quantised.** Chosen so the repo runs anywhere without PyTorch. A larger model would retrieve better.
- **Chunking is one chunk per item.** Long SEC filings are truncated rather than split, so a fact buried deep in a 10-K may be unreachable.
- The system will say "insufficient evidence" for questions a human could answer from general knowledge. That is intended, and it is measured — see [`EVALUATION.md`](EVALUATION.md).

## Evaluation

- **15 questions is a small suite.** It is a regression harness, not a benchmark.
- **Expected values are corpus-specific constants** (`count_recruiting`: 90, `count_terminated`: 71, `top_sponsor`: Novo Nordisk/105, `corpus_size`: 1399). Re-ingesting invalidates them, and the suite will fail loudly rather than silently pass.
- **Extraction precision/recall, dedup cluster purity and diff correctness are not measured.** The concept note names them; this build does not evaluate them, because the single-backfill corpus produces no diffs and no duplicate clusters to score.
- **The calibration claim is not yet measured.** Reviewer feedback is captured (`item_review`), but the loop that turns it into changed feature weights and routing priors is not wired. Precision@10 before and after calibration is therefore an untested claim in this build.

## Not built

- **The Expectation Ledger and silence signals.** Specified to implementation readiness and seeded with 134 real forward-dated commitments, but the watch loop has never run. See [`docs/EXPECTATION_LEDGER.md`](docs/EXPECTATION_LEDGER.md).
- **Entity resolution across sources.** A sponsor is matched by normalised name, not by a resolved entity id. "Baxalta now part of Shire" and "Shire" are reconciled by an explicit alias rule, not by a general mechanism.
- **Event deduplication across sources.** Near-duplicate clustering is described in the concept note; this build deduplicates exactly, on `(source_name, source_id)`, within a source only.
- **Authentication, multi-user state, and audit logging.** The prototype has no login and no per-user roles beyond a client-side role selector.

## Scope, deliberately

No confidential or internal Novo Nordisk data is used or required. No patient-level data. No pharmacovigilance case intake, adverse-event reporting or regulatory submission. Nothing here constitutes clinical, prescribing or investment advice. See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).
