# Phase 1b — Classification

Assigns an evidence-status verdict to every ingested record. Sits between Phase 1 ingestion and Phase 2 retrieval, writing to the `classifications` table in the Phase 1 database.

```
raw_items  ->  validate  ->  rules layer  ->  [LLM fallback]  ->  classifications
```

---

## The four categories

| Category | Meaning |
|---|---|
| `proven_right` | Results independently confirmed — meta-analysis, replication, or a strong RCT with no contradicting evidence |
| `proven_false` | Results contradicted, trial failed or terminated, or the paper retracted |
| `proven_false_but_useful` | Failed or retracted, but the data has been cited or reused for other findings |
| `still_working_on` | Preprint, early phase, or recruiting with no established results yet |

## Two layers, in that order

**1 · Rules** (`paper_validator.py:rules_layer`) — deterministic, auditable, free, and always tried first. A verdict that can be derived from a structured field should never cost an API call, and should never vary between runs.

**2 · LLM** (`llm_classifier.py`) — only for what the rules cannot reach. The model returns strict JSON, which is parsed and validated against the category set. An unparseable or out-of-vocabulary reply is recorded as a failure with its reason, never coerced into a guess.

`classify_with_council()` runs several models and requires a strict majority; disagreement is recorded as a failure with every vote listed, rather than resolved by picking one. `main.py` uses the single-model path.

## What actually resolves today

Against the current 1,399-record corpus:

| Layer | Records | Detail |
|---|---|---|
| Rules | **161** | 90 `RECRUITING` → `still_working_on`, 71 `TERMINATED` → `proven_false` |
| LLM | 1,238 | Everything else, one call each |

## The dependency gap — read this before trusting a verdict

`rules_layer` branches on `retracted`, `citation_count` and `publication_type`. **No ingestor collects any of the three.** `database_adapter.py` therefore supplies `retracted=False`, `citation_count=0`, `publication_type="unknown"` for every record, and the branches depending on them are dead by construction — including the only path that can ever produce `proven_false_but_useful`.

The LLM receives those same defaults in its prompt, so it is being told every paper is un-retracted and uncited regardless of truth.

Closing this needs a Crossref or OpenAlex enrichment step in Phase 1. It is not in this build, and the consequence is recorded in [`../LIMITATIONS.md`](../LIMITATIONS.md).

Additionally, `WITHDRAWN`, `SUSPENDED`, `NOT_YET_RECRUITING` and `ACTIVE_NOT_RECRUITING` are unmapped in the rules layer and fall through to the LLM. Mapping them is a judgement about clinical semantics, not a code gap.

## Running it

```bash
cd llm_1
../data-ingestion-system/.venv/bin/python main.py --limit 50    # smoke test
../data-ingestion-system/.venv/bin/python main.py               # full run
```

Configuration comes from the **shared `.env` at the repository root** —
`llm_1/.env` is a symlink to it, so this classifier and the Phase 2 assistant
use the same endpoint and the same `LLM_API_KEY`. Set `LLM_BASE_URL` to point
both at Gemini, Groq, OpenRouter or a local Ollama; leave it blank for
HuggingFace serverless.

Run from inside `llm_1/`. `main.py` puts the sibling `data-ingestion-system/` on `sys.path` and defaults `DATABASE_URL` to the database next to it; override `DATABASE_URL` to point elsewhere.

Requires migration `002_classifications` to have been applied:

```bash
cd ../data-ingestion-system && .venv/bin/python -m alembic upgrade head
```

## How Phase 2 consumes this

Phase 2 reads `classifications` **live** rather than indexing it (`phase2/api/classifications.py`), so re-running the classifier is reflected immediately with no index rebuild. If the table is absent, every verdict-dependent feature degrades to "no verdict" rather than failing — the `VerdictBadge` renders empty and `VERDICT_WEIGHTS` contributes a neutral 1.00.

Verdicts nudge urgency; they never dominate it. The spread in `phase2/api/signals.py:122` is 1.00–1.10, and a record with no verdict is not penalised for lacking one.

The data contract is documented in [`../FRONTEND_INTEGRATION.md`](../FRONTEND_INTEGRATION.md).

## Files

| File | Role |
|---|---|
| `main.py` | Orchestration and CLI |
| `paper_validator.py` | Input validation + the rules layer |
| `llm_classifier.py` | HuggingFace client, prompt, JSON parsing, council voting |
| `database_adapter.py` | Maps a `raw_items` row to the validator's input contract |

`test_rules_layer.py` and `test_database_classifier.py` are manual exercise scripts, not pytest suites — they contain no collectible test functions.
