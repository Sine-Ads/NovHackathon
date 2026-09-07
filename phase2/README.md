# Phase 2 — Stakeholder Intelligence UI

Turns the Phase 1 corpus into something a stakeholder can browse, question and
decide from: a searchable feed, cards that expand into AI summaries, a chatbot
scoped to one record and its neighbours, and a global assistant with reach over
everything monitored.

Phase 2 lives entirely in this folder. **No file in `data-ingestion-system/` or
`llm_1/` is modified**, and the Phase 1 database is opened read-only — enforced
by SQLite's `mode=ro`, not by convention.

---

## Quick start

```bash
cd phase2
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then add your HF_TOKEN

python scripts/check_env.py   # do this first — proves the right DB is found
python scripts/build_index.py # ~8 min once (embeds 1,399 records)

python -m uvicorn api.main:app --port 8000
```

In a second terminal:

```bash
cd phase2/web
npm install
npm run dev                   # http://localhost:3000
```

Browsing and search work without an `HF_TOKEN`. Summaries and both chatbots
need one — get a free token at <https://huggingface.co/settings/tokens>.

---

## How it works

```
Phase 1 haemophilia_data.db  (read-only, never written)
        |
        v
scripts/build_index.py  ->  data/phase2.db   FTS5 + embeddings + caches
        |
        v
FastAPI  :8000            Next.js  :3000
```

### Retrieval is four stages, not one

```
query
  |- FTS5 BM25 ----+
  |- vector cosine +--> RRF fusion --> metadata filters --> evidence ranking --> LLM
```

Fusion is Reciprocal Rank Fusion: BM25 scores and cosine similarities sit on
incomparable scales, so only the ranks are used and there is nothing to tune.

Evidence ranking is the layer that separates *search* from *intelligence*.
Relevance stays dominant; completeness and recency are bounded multipliers:

| Factor | Range | Rule |
|---|---|---|
| completeness | 0.60 / 0.85 / 1.00 | stubs rank lower but never vanish |
| recency | 0.90 – 1.10 | applied **only** to real publication and filing dates |

Recency is deliberately neutral for ClinicalTrials.gov, because that source
stores a study *start* date — nine records are dated into 2027, and a planned
start is not a publication event. The ±10% band is narrower than typical gaps
between adjacent RRF ranks, so recency breaks ties without ever overriding
relevance.

### Provenance is first-class

Retrieval returns `Evidence` objects, never bare ids. Each carries the source,
identifier, permalink, date semantics, both ranks, the cosine score, every
factor applied, and a `reason` string such as:

> matched on both keyword (#3) and meaning (#1, similarity 0.87)

`reason` is assembled deterministically from the scoring fields. No model writes
it, so it cannot be fabricated. It is stored with each chat turn, so a reloaded
conversation still shows what it stood on.

### Numbers never come from the model

Top-k retrieval sees eight documents and physically cannot answer "how many
trials are recruiting". Two mechanisms prevent a guess:

1. **Landscape block** — deterministic aggregates over all 1,399 rows, injected
   into every global-chat prompt.
2. **Whitelisted aggregates** (`api/aggregates.py`) — a fixed set of
   parameterised queries. The model names one; it never writes SQL. Tool
   round-trips are capped at one.

Condition and sponsor labels are normalised before counting. `Hemophilia A` and
`Haemophilia A` are one condition (454 records, not 361), and "Baxalta now part
of Shire" is one sponsor.

### Confidence, and the willingness to decline

| Level | Meaning |
|---|---|
| `supported` | every claim traces to an excerpt or an exact count |
| `inferred` | synthesised across records; no single excerpt says it |
| `insufficient` | the corpus cannot support an answer |

Confidence is not the model's to award itself. A deterministic gate runs
*before* generation: with no evidence, evidence below `MIN_EVIDENCE`, or
nothing but stubs, **no LLM call is made at all** and a templated reply names
what was missing. After generation, a `supported` claim with no citations — or
citing records that were never retrieved — is demoted. Self-report can lower
confidence, never raise it.

### Scope and memory boundary

| Scope | Evidence | History |
|---|---|---|
| item | that record + its nearest neighbours | that record's thread only |
| global | landscape + facts + hybrid top-k | the global thread only |

Threads never merge. Retrieval reruns from scratch every turn, so a fact seen in
turn 2 is not available in turn 5 unless turn 5 retrieves it again. Only `role`
and `content` are replayed — prior evidence blocks are never resent, so stale
context cannot masquerade as current retrieval.

---

## Classifier verdicts (Phase 1 revision 002)

Phase 1 gained a `classifications` table — one verdict per record: `proven_right`,
`proven_false`, `proven_false_but_useful`, `still_working_on`. Phase 2 reads it
per the contract in `FRONTEND_INTEGRATION.md`:

- **Read live, never indexed.** The classifier runs on its own schedule, and a
  verdict copied into the sidecar would go stale without the content hash ever
  noticing. Re-running the classifier is reflected on the next request.
- **Optional by design.** A database still on revision 001 is valid. Every
  classification call degrades to "no data" rather than raising, so verdict
  badges and filters simply stay hidden. `/api/health` says which state you are
  in; `POST /api/classifications/recheck` picks the table up without a restart.
- **A failed attempt is not a category.** The document asks for failures to stay
  visible to operators without being presented as a result, so a failed row
  renders grey as "Unclassified" with its reason, is excluded from every
  category count, and is filterable only through a separate chip.
- **A verdict is a data field, not a truth claim.** Both assistants receive the
  verdict, what it means, and who assigned it (`rule` or `llm`), plus an explicit
  instruction not to upgrade it into a stronger claim than it makes — it is
  derived from publication type, retraction flag and citation count, not from an
  appraisal of the evidence. Absence of a verdict is never a negative verdict.

### Endpoints from the integration document

`FRONTEND_INTEGRATION.md` specifies `GET /papers`, `GET /papers/{raw_item_id}`
and `GET /categories/{category}` with a flat shape keyed on `id`, `source`,
`abstract`, `published_at`. The radar's own endpoints use different names
(`item_id`, `source_name`, `raw_content`, `date_published`) and carry more
detail, so rather than renaming those and breaking the UI, Phase 2 serves the
documented shape alongside them:

| Endpoint | Shape |
|---|---|
| `GET /api/papers?limit=&offset=&status=` | document shape, newest verdict first |
| `GET /api/papers/{raw_item_id}` | document shape, one record |
| `GET /api/categories/{category}` | document shape, filtered; accepts `failed` |
| `GET /api/feed?category=` | radar shape, verdict attached to each card |

Anything written against the document works unchanged.

---

## The signal view

The feed reads the same corpus as a stream of *events* rather than a list of
documents: urgency, category, indication, and what has been observed to change.
Nothing here is a new ingestion — every field is derived from stored data, and
anything the corpus cannot support is absent rather than guessed.

| Derived field | Where it comes from |
|---|---|
| `category` | The source: ClinicalTrials.gov → Trial, PubMed/arXiv → Publication, SEC EDGAR → Corporate |
| `indication` | Haemophilia A / B wording in the title and metadata; `null` when the record names neither |
| `urgency` | completeness x recency x change x verdict, bucketed |
| `what_changed` | The observation log below; `null` until something has moved |
| `reviewed` | A human decision, stored in the sidecar |

Urgency reuses `evidence.completeness_factor` and `evidence.recency_factor`
unchanged, so a record cannot be urgent in the feed and unremarkable in search.
The card's "why this urgency" panel prints the actual multipliers — multiply the
column and the score comes back.

The thresholds are calibrated against the corpus, not chosen in the abstract.
With completeness capped at 1.00 and recency at 1.10, a record that has never
been observed to change tops out at 1.07, so `HIGH` sits at 1.02: today that
band is the 28 complete records carrying a real publication or filing date, and
a trial that changes status (x1.50) clears it outright.

**Fields the radar design carried that this corpus cannot support — geography,
modality, and per-team review routing — are not in the type.** Phase 1 ingests
none of them. An empty field is a fact about the corpus; an invented one is not.
For the same reason the category list has three values and not eight: there is
no regulatory, HTA, congress or safety source behind the others, and the filter
rail is driven by facet counts so it can only ever offer what exists.

### Change detection

Phase 1 stores one row per source record, unique on `(source_name, source_id)`,
with no revision table — so a field's history only exists if Phase 2 watches for
it. Three sidecar tables do that, and the Phase 1 file stays byte-identical:

| Table | Holds |
|---|---|
| `item_snapshot` | the watched fields at each distinct content hash |
| `item_change` | one row per field that moved, with when it was noticed |
| `item_review` | whether a human has marked the record reviewed |

`build_index.py` records an observation for every record on every run, before
the unchanged-hash shortcut — an index built before this existed has no
snapshots at all, and re-observing a known hash writes nothing. Watched fields
are `overall_status`, `lead_sponsor` and `conditions` for trials, `form` and
`period_ending` for filings, `doi` and `journal` for literature, plus the title
everywhere; the rest of each source's metadata is a static identifier.

A first appearance is recorded as a real, dated observation
(`record: first seen`, dated by Phase 1's `date_ingested`) rather than left
blank — so the view has honest content on the first run, and true field-level
diffs accumulate on top of it from the second run onward. Today every record is
in that first state: the corpus was loaded in a single backfill, so ordering by
detection date is ordering within that one run, and the UI says so instead of
implying a spread.

`--rebuild` drops the index but deliberately keeps these three tables. They
record what was observed when, and a human's review decisions; discarding them
would make every record look newly seen and silently rewrite the history.

### Endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/signals` | the feed; same filters as `/api/feed` plus `kind`, `urgency`, `indication`, `reviewed`, `changed_only` |
| `GET /api/signals/{item_id}` | one signal with its full change history and evidence |
| `POST /api/signals/{item_id}/review` | toggles the reviewed flag |
| `GET /api/facets` | gains `kinds`, `urgencies`, `indications` and the review counts |

`/api/feed`, `/api/items/*`, `/api/papers*` and both chat endpoints are
unchanged, so anything written against them keeps working.

Urgency and indication are computed rather than stored, so those two filters and
the urgency sort are applied after the SQL filters have cut the set down. At
1,399 records that is one cheap pass; past a few tens of thousands they become
columns on `item` written at index time.

A search is never re-sorted. Asking for the best match and getting the answer
reordered by urgency would misrepresent the ranking, so the sort control is
disabled while a query is active.

---

## Data-quality handling

These are Phase 1 behaviours. That code is off-limits, so Phase 2 works around
them honestly rather than hiding them.

| Reality | Handling |
|---|---|
| `date_published` means different things per source | Every card labels it: "Study start", "Published", "Filed" — never a bare date |
| 9 trials dated into 2027 | Kept, badged "Planned start", given no recency bonus |
| 268/299 PubMed rows undated | `ORDER BY date_published IS NULL, date_published DESC`; UI shows "Date unknown" |
| 100 SEC stubs + 51 thin PubMed rows | Templated summary, `abstain`, **no LLM call** — cannot hallucinate |
| `interventions[]` empty for all 992 trials | No drug facet; drug queries go through full-text (emicizumab → 87 hits) |
| Condition/sponsor spelling variants | Normalised in aggregates only; raw strings preserved on cards |
| OpenFDA carries two record types | Branches on `metadata.type`; ready for when that ingestor returns rows |
| Classifier needs `retracted` / `citation_count`, which no ingestor collects | Records stay unclassified rather than mis-verdicted; the UI says so |

All 1,399 rows were ingested in a single backfill, so while every record now
carries a real first-seen date, they are all from that one run — the detection
axis exists but is flat until a second ingestion, and the feed says so rather
than implying a spread.

---

## Evaluation

```bash
python scripts/run_eval.py
python scripts/run_eval.py --category insufficient_evidence
```

Fifteen golden questions across six categories, with machine-checkable
expectations: factual counts, semantic search, source-specific behaviour,
insufficient evidence, cross-document comparison, citation correctness, and item
scope. Expectations key on stable identifiers (NCT numbers), not sidecar UUIDs.

The `insufficient_evidence` cases matter most. Asking for Hemlibra's German
reimbursement price, or which drug `NCT01395810` used, are both questions this
corpus genuinely cannot answer — no pricing data was ever ingested, and
`interventions[]` is empty for every trial. **Abstention recall is reported
separately**, because confidently answering these is the worst failure the
system has.

---

## Layout

```
api/
  config.py       paths resolved from __file__, never cwd
  source_db.py    read-only Phase 1 access
  store.py        sidecar schema (chunk-keyed)
  chunker.py      metadata flattening + chunking (1 chunk/item today)
  classifications.py  read-only verdicts; degrades when the table is absent
  embed.py        fastembed ONNX + in-memory vector index
  evidence.py     Evidence dataclass + evidence ranking
  signals.py      derived category, indication, urgency; facet counts
  retrieval.py    FTS + vector + RRF + rollup
  router.py       aggregate | retrieval | both
  aggregates.py   whitelisted SQL, no model-written queries
  landscape.py    corpus statistics, normalised
  confidence.py   pre-generation gates + post-generation validation
  llm.py          HF Inference wrapper, JSON repair
  prompts.py      summary / item chat / global chat
  summarize.py    on-demand summaries with caching + abstention
  chat.py         orchestration, scope and memory boundary
  main.py         FastAPI routes + SSE
scripts/          check_env.py, build_index.py, run_eval.py
eval/golden.yaml  the golden question set
web/
  app/            shell, radar feed, signal detail, assistant
  components/     signal views (Tailwind) + record views (plain CSS)
  hooks/          react-query access to the signal endpoints
  lib/            API client, types, role presets, failure copy
```

The frontend runs two styling systems on one palette: the shell, feed and signal
detail are Tailwind, while the summary panel, both chatbots and the confidence
badges keep the plain CSS they shipped with. `tailwind.config.ts` and the
variables at the top of `app/globals.css` hold the same values, so the two
cannot drift.

### Chunk-ready by design

Every table and retrieval signature is keyed on `chunk_id`, though the corpus
currently produces exactly one chunk per record (average 1.2k characters).
Retrieval already rolls chunks up to records — an identity operation today. When
long documents arrive, split them in `chunker.chunk_item()` and nothing else
changes.

---

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `HF_TOKEN` | — | required for summaries and chat |
| `PHASE2_LLM_MODEL` | `Qwen/Qwen2.5-72B-Instruct` | alternate: `meta-llama/Llama-3.3-70B-Instruct` |
| `PHASE2_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | 384-dim, ONNX |
| `PHASE2_SOURCE_DB` | auto | absolute path wins over auto-resolution |
| `MIN_EVIDENCE` | `0.008` | below this the assistant declines without calling the LLM |
| `PHASE2_EMBED_THREADS` | `4` | raising this raises indexing memory |
| `PHASE2_EMBED_BATCH` | `16` | ditto |

**On embeddings:** this uses `fastembed` (ONNX Runtime), not
`sentence-transformers` (PyTorch). They are different libraries on different
runtimes and their vectors are not interchangeable — switching means a full
re-embed. What carries over is that embeddings stay local: no embedding API, no
network at query time. fastembed installs in ~120 MB against PyTorch's ~1.2 GB,
which is what made it the right call here.

Indexing is memory-bounded on purpose. fastembed's defaults fork workers that
each load the model; unconstrained, that reached 4.1 GB RSS and was OOM-killed
on a 14 GB machine with no swap. With `parallel=1`, batch 16 and 4 threads it
peaks at 376 MB and takes about 8 minutes for 1,399 records.

---

## Verifying Phase 1 is untouched

```bash
md5sum ../data-ingestion-system/haemophilia_data.db   # before and after
cd ../data-ingestion-system && python run.py --list-ingestors

python -c "
import sqlite3
c = sqlite3.connect('file:$PWD/../data-ingestion-system/haemophilia_data.db?mode=ro', uri=True)
print(c.execute('select count(*) from raw_items').fetchone())
c.execute('create table x(y)')   # must raise OperationalError
"
```
