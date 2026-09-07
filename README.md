# Haemophilia Intelligence Radar

**Detects what changed, explains why it matters, names who reviews it, and proposes what action is required.**

A persistent, structured view of the haemophilia landscape that diffs new information against stored prior state. It does not report "an article mentioned a trial"; it reports `NCT0XXXXXXX · Phase 2 → Phase 3`, with the source span that proves it, the function that owns it, and a dated action.

Built for the Novo Nordisk Rare Disease Hackathon by **Catalyst**, Manipal Institute of Technology Bengaluru.

---

## Why this is not a news dashboard

A summariser answers *"what does this document say?"*. That question is already well served, and it misses the thing that actually costs money: **late recognition of change**.

The same development appears across registries, filings and journals in different formats on different days. A competitor programme crossing into Phase 3, an HTA rejection in a reference market, a readout that was promised and never delivered — none of these is a headline. The first is a registry *field change*. The last produces no document at all, so no summariser can ever surface it.

This system maintains state and reports transitions against it.

---

## What is actually built

Status is stated honestly throughout this repository. Nothing below is aspirational.

| Capability | Status | Where |
|---|---|---|
| Multi-source ingestion, 8 connectors | **Built** — 4 returned data | `data-ingestion-system/` |
| Versioned snapshots + change log | **Built** | `phase2/api/store.py`, `item_snapshot` / `item_change` |
| Rules + LLM classification | **Built** — rules layer live, LLM stage needs a token | `llm_1/` |
| Hybrid retrieval (FTS5 + vector + RRF) | **Built** | `phase2/api/retrieval.py` |
| Evidence ranking with provenance | **Built** | `phase2/api/evidence.py` |
| Confidence gate and abstention | **Built** | `phase2/api/confidence.py` |
| Urgency scoring + role routing | **Built** | `phase2/api/signals.py` |
| Feed / signal detail / assistant UI | **Built** | `phase2/web/` |
| Golden-set evaluation harness | **Built** | `phase2/eval/`, `phase2/scripts/run_eval.py` |
| Expectation Ledger + silence signals | **Designed, schema frozen** | [`docs/EXPECTATION_LEDGER.md`](docs/EXPECTATION_LEDGER.md) |
| Stakeholder calibration loop | **Partial** — feedback captured, re-weighting not wired | `item_review` |

See [`LIMITATIONS.md`](LIMITATIONS.md) for what this corpus cannot support and why.

---

## The corpus, as it stands

1,399 records, ingested in a single backfill on 2026-09-01.

| Source | Records | Note |
|---|---|---|
| ClinicalTrials.gov (API v2) | 992 | `haemophilia OR hemophilia` |
| PubMed (NCBI E-utilities) | 299 | |
| SEC EDGAR full-text | 100 | Haemophilia-active issuers |
| arXiv | 8 | |
| OpenFDA | 0 | Connector built; no matching records returned |
| WHO ICTRP | 0 | Export endpoint blocks automated access |
| medRxiv | 0 | Connector built; no matching records returned |
| USPTO | 0 | Requires `USPTO_API_KEY` |

Top sponsors in the trial set: Novo Nordisk A/S (105), Bayer (58), Baxalta/Shire (54), Pfizer (43), CSL Behring (29).

---

## Architecture

Three stages, two SQLite databases, one hard boundary.

```
   Public sources (allowlisted)
            |
 [ 1 ] data-ingestion-system/     8 async ingestors, APScheduler, no AI by design
            |                     -> haemophilia_data.db   (raw_items, ingestor_logs,
            |                                               scheduling_metadata, classifications)
            |
 [ 2 ] llm_1/                     deterministic rules layer, then LLM fallback
            |                     -> classifications table (same database)
            |
            |  ==== opened read-only, mode=ro, never written ====
            v
 [ 3 ] phase2/                    chunk + embed + FTS5 index
                                  hybrid retrieval -> evidence ranking -> confidence gate
                                  urgency scoring -> role routing -> signal cards
                                  -> phase2/data/phase2.db  (sidecar; all writes land here)
                                  -> FastAPI (18 endpoints) + Next.js 14 UI
```

**The boundary is enforced, not agreed.** Phase 2 opens Phase 1's database with SQLite's `mode=ro` URI flag; a stray write raises rather than corrupts. Every Phase 2 write goes to its own sidecar. This is why Phase 1 can be re-run or replaced without touching Phase 2.

Full detail: [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Running it

Every command, in order, with nothing assumed: [`RUNBOOK.md`](RUNBOOK.md).

**Configuration is one `.env` at the repository root**, gitignored and never committed. `phase2/.env`, `llm_1/.env` and `data-ingestion-system/.env` are symlinks to it, so every component — including both model stages — shares a single `LLM_API_KEY`.

The short version:

```bash
# Configuration — create .env at the root, then link all three components to it
ln -sf ../.env phase2/.env && ln -sf ../.env llm_1/.env && ln -sf ../.env data-ingestion-system/.env

# Phase 1 — database ships populated; this only rebuilds it
cd data-ingestion-system && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head

# Phase 2 — the demo (reads the same root .env)
cd ../phase2 && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/check_env.py
.venv/bin/python scripts/build_index.py
.venv/bin/python -m uvicorn api.main:app --port 8000

cd web && npm install && npm run dev     # http://localhost:3000
```

Browsing, search and filtering work with no token. Summaries and both chatbots need one.

---

## Technology

| Layer | Choice | Why |
|---|---|---|
| Ingestion | Python 3.10, httpx, SQLAlchemy 2.0 async, APScheduler | Async fan-out across 8 sources |
| Storage | SQLite + FTS5 | Ships in the repo; a judge clones and runs with no server |
| Embeddings | fastembed (ONNX), `bge-small-en-v1.5`, 384-dim | No PyTorch — 90 MB instead of 2.5 GB |
| Retrieval | BM25 + cosine, fused with Reciprocal Rank Fusion | Neither alone was sufficient; see `ARCHITECTURE.md` |
| Generation | Any OpenAI-compatible endpoint (Gemini, Groq, OpenRouter, local Ollama) | Provider is two `.env` lines; structured output with deterministic fallback |
| API | FastAPI + SSE | Token streaming with a withholding buffer |
| Web | Next.js 14, React 18, TanStack Query, Tailwind | |

Decision records, including the alternatives rejected: [`docs/adr/`](docs/adr/).

---

## Evaluation

15 golden questions across 6 categories, including three that **must** be refused. Abstention recall is reported separately from accuracy and gates the exit code — a system that answers a question it cannot support fails the suite even if every other answer is right.

Methodology and results: [`EVALUATION.md`](EVALUATION.md).

---

## Repository layout

```
data-ingestion-system/   Phase 1 — ingestion. Frozen. README.md
llm_1/                   Phase 1b — classification. README.md
phase2/                  Phase 2 — retrieval, scoring, API, UI. README.md
docs/
  EXPECTATION_LEDGER.md  The designed anticipatory-watch capability
  adr/                   Architecture decision records
  deck/                  Final presentation deck
ARCHITECTURE.md          As-built system design
RUNBOOK.md               End-to-end run order
EVALUATION.md            Golden set, method, results
LIMITATIONS.md           What this does not do, and why
FRONTEND_INTEGRATION.md  Classifier -> frontend data contract
```

---

## Team

Manipal Institute of Technology, Bengaluru — **Catalyst**

Student lead: Ch. Achyuth · Anagha Ravindran · Nishita Pagaku · Krishna Gunjan · Aditya Alur
Faculty mentor: Dr. Sravani Vemulapalli

## Data policy

Public APIs, feeds and listings only. No confidential or internal Novo Nordisk data is used or required. Every claim carries a source URL and a supporting quote; unsupported claims are withheld rather than generated. Synthetic documents, where used, are labelled as such in the interface. See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).
