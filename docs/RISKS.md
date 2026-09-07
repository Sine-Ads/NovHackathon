# Risk register

| # | Risk | Likelihood | Impact | Mitigation in this build | Residual |
|---|---|---|---|---|---|
| R1 | A public source changes its API or blocks automated access | High | High | Each ingestor is isolated behind one `BaseIngestor` contract; a failure is logged to `ingestor_logs` and does not stop the run | WHO ICTRP already blocks us — the risk is realised, not hypothetical |
| R2 | Rate limiting or IP blocking under production volume | Medium | High | `tenacity` backoff, per-ingestor intervals, `max_instances=1`, identifying User-Agent on SEC | Untested above backfill volume |
| R3 | Model provider changes, deprecates, or prices out the inference endpoint | Medium | Medium | Model is a config value; the LLM is confined to `api/llm.py` behind one interface | A swap requires re-running the eval suite to re-baseline |
| R4 | The model fabricates a claim or a number | Medium | **Critical** | Numbers come from whitelisted aggregates, never generation (ADR 004); claims failing provenance validation are withheld; confidence gate runs before generation (ADR 006) | Free-text *reasoning* between cited facts is still model-generated |
| R5 | Silence signals assert an absence that is false | Medium | High | Every probe is logged; the silence card cites the probe log, not a belief | Absence is only as good as source coverage — a gap in the allowlist looks like silence |
| R6 | Corpus staleness — single backfill, scheduler never re-run | **Realised** | High | Scheduler implemented and tested; cursors persist for resumable runs | Every record sits at "first seen"; no real diffs exist yet |
| R7 | Eval constants are corpus-specific and break on re-ingestion | High | Low | The suite fails loudly rather than silently passing | Constants must be re-baselined after every ingestion |
| R8 | Classifier verdicts rest on fields no ingestor collects | **Realised** | Medium | Documented in `llm_1/README.md`; verdict weight spread capped at 1.00–1.10 so a wrong verdict cannot dominate | `proven_false_but_useful` is unreachable |
| R9 | Source terms of service restrict derived redistribution | Low | Medium | Public endpoints only; metadata and permalinks stored, no full text scraped, no paywalled access | Not reviewed by counsel |
| R10 | A sensitive signal (safety, competitive) is acted on without human review | Low | **Critical** | Such signals are flagged for mandatory human review before being shown as actionable; the system never communicates externally | Enforced by policy and UI, not by a hard technical control |
| R11 | Scaling past ~10⁵ records | Low now | Medium | Schema is portable; vector search is the first thing to break (full scan) | Migration to Postgres + pgvector deferred, ADR 001 |
| R12 | Single-contributor knowledge concentration | Medium | Medium | Decisions recorded in `docs/adr/`; runbook tested from a clean clone | Hackathon timeframe |
