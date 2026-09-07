# Evaluation

A regression harness, not a benchmark. 15 golden questions across 6 categories, defined declaratively in [`phase2/eval/golden.yaml`](phase2/eval/golden.yaml) and run by [`phase2/scripts/run_eval.py`](phase2/scripts/run_eval.py).

```bash
cd phase2 && .venv/bin/python scripts/run_eval.py
```

Requires `LLM_API_KEY` — the suite exercises generation and routing, not retrieval alone.

---

## What is tested

| Category | Q | What a pass demonstrates |
|---|---|---|
| `factual_count` | 4 | Counts come from whitelisted aggregates over all 1,399 rows, never from a model reading eight retrieved documents |
| `semantic_search` | 2 | Paraphrased questions retrieve the right records without keyword overlap |
| `source_specific` | 1 | Source filters are honoured rather than approximated |
| **`insufficient_evidence`** | **3** | **The system refuses rather than guessing** |
| `cross_document` | 2 | Synthesis across records is labelled `inferred`, not `supported` |
| `citation_correctness` | 1 | Every citation resolves to a record that was actually retrieved |
| `item_scope` | 2 | Item-scoped chat cannot reach outside its own record |

## Assertion vocabulary

Assertions are declarative, so adding a regression case is a YAML entry rather than code:

| Assertion | Checks |
|---|---|
| `expect_route` | The intent router chose aggregate / retrieval / both correctly |
| `expect_numbers` | Exact numeric values appear in the answer |
| `expect_contains` | Required substrings are present |
| `expect_absent` | Forbidden substrings are **not** present |
| `expect_confidence` | The confidence level is exactly as expected |
| `must_retrieve_any_of` | At least one required record reached the evidence set |
| `assert_citations_valid` | Every citation maps to a retrieved item id |
| `scope` | Item vs global scope enforcement |

## Abstention recall gates the run

Reported separately from accuracy, and it controls the exit code: **if the system answers any question it should have refused, the suite fails regardless of every other result.**

This is deliberate. In a decision-support tool for a regulated industry, a confident wrong answer is worse than no answer, so the metric that matters most is not accuracy — it is the refusal rate on questions the corpus cannot support.

## Results

> **Not yet recorded.** The suite has not been run against this build because
> the shared root `.env` currently carries an empty `LLM_API_KEY`. Populate it and run the
> command above; paste the per-category table and the abstention-recall line here.
>
> Record the run date and the corpus size alongside the numbers — both are needed
> to interpret them, and the expected values below are corpus-specific.

| Category | Passed | Total |
|---|---|---|
| factual_count | — | 4 |
| semantic_search | — | 2 |
| source_specific | — | 1 |
| insufficient_evidence | — | 3 |
| cross_document | — | 2 |
| citation_correctness | — | 1 |
| item_scope | — | 2 |
| **Abstention recall** | **—** | must be 1.0 |

## Corpus-specific constants

The suite hard-codes values derived from this exact corpus:

| Constant | Value |
|---|---|
| `corpus_size` | 1,399 |
| `count_recruiting` | 90 |
| `count_terminated` | 71 |
| `top_sponsor` | Novo Nordisk A/S, 105 trials |

**Re-ingesting invalidates all four.** The suite will fail loudly rather than silently pass, which is the intended behaviour — but the constants must be re-baselined after every ingestion run.

## What is not measured

Named in the concept note, absent from this build, and absent for a stated reason:

| Metric | Why not |
|---|---|
| Extraction precision / recall | No labelled gold set of extracted fields exists |
| Dedup cluster purity | Deduplication is exact-match within a source; there are no near-duplicate clusters to score |
| Diff correctness | Every record is at "first seen" — a single backfill produces no diffs |
| Precision@10 before vs after calibration | Feedback is captured (`item_review`); the re-weighting loop is not wired |
| Mean urgency error | Requires reviewer-labelled urgency, which requires the calibration sessions requested in the deck |

Each becomes measurable after a specific, identified change — a second ingestion run for the first three, the calibration loop for the last two. None is blocked on a redesign.

## Unit tests

```bash
cd data-ingestion-system
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -v
```

13 tests covering ingestor parsing (8, with HTTP mocked via `respx`), database CRUD and idempotency (3), and scheduler setup and its concurrency guard (2).

Phase 2 has no unit tests; the golden suite is its regression harness. `llm_1/test_*.py` are manual exercise scripts with no collectible test functions.
