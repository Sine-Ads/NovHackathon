# Architecture decision records

Each record states the decision, the alternative that was rejected, and what it costs. Decisions are dated and not rewritten; a reversal gets a new record.

| # | Decision | Cost accepted |
|---|---|---|
| [001](001-sqlite-over-postgres.md) | SQLite + FTS5, not PostgreSQL + pgvector | No concurrent writers, no server-side scaling |
| [002](002-fastembed-over-sentence-transformers.md) | fastembed ONNX, not sentence-transformers | Smaller model, fewer embedding options |
| [003](003-phase-1-frozen-read-only.md) | Phase 1 frozen, opened `mode=ro` | Duplicated derived state in a sidecar |
| [004](004-model-names-a-query-never-writes-sql.md) | The model names a whitelisted query; it never writes SQL | Only anticipated aggregates are answerable |
| [005](005-one-tool-round-trip.md) | Tool round-trips capped at exactly one | Multi-hop questions cannot be answered |
| [006](006-confidence-gate-before-generation.md) | Deterministic confidence gate before generation | Refuses some questions a human could answer |
| [007](007-rrf-over-weighted-fusion.md) | Reciprocal Rank Fusion, not weighted score fusion | Discards score magnitude |
| [008](008-trials-held-recency-neutral.md) | ClinicalTrials.gov held recency-neutral | Genuinely recent trials get no recency boost |
