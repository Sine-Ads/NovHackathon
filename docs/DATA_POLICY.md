# Data policy

## What is used

Public APIs, feeds and listings only, against a fixed allowlist:

| Source | Access | Terms |
|---|---|---|
| ClinicalTrials.gov API v2 | Public, no auth | US Government work, public domain |
| PubMed / NCBI E-utilities | Public, no auth | NCBI usage policy; rate limits respected |
| SEC EDGAR full-text search | Public, no auth | SEC fair-access policy; identifying User-Agent sent |
| arXiv Atom API | Public, no auth | arXiv API terms; metadata only |
| OpenFDA | Public, no auth | US Government work, public domain |
| WHO ICTRP | Public listing | Blocked to automated access; no data collected |
| medRxiv | Public API | Metadata only |
| USPTO | API key required | Not held; no data collected |

Only titles, abstracts, structured metadata and permalinks are stored. Full-text article bodies are not scraped, and no paywalled content is accessed.

## What is not used

**No confidential or internal Novo Nordisk data is used, required, or would be required to run this system.** Where a Novo Nordisk asset appears in the corpus, it appears because it is in a public registry or filing — the trial set contains 105 Novo Nordisk-sponsored studies, all publicly registered.

Also out of scope: patient-level data of any kind; pharmacovigilance case intake; adverse-event reporting; regulatory submission; automated external communication; and any clinical, prescribing or investment recommendation.

## Provenance and abstention

Every rendered claim carries a source URL and an exact supporting quote. A claim that fails provenance validation is not rendered; the system shows an explicit `insufficient evidence` state instead of a confident assertion. This is enforced before generation by a deterministic gate, not by prompt instruction — see [`../phase2/README.md`](../phase2/README.md).

## Synthetic data

Where synthetic documents are used to exercise capabilities the live corpus cannot reach — silence detection, calibration demonstrations — they are **labelled `SYNTHETIC` in the interface** and are never mixed into counts or aggregates over the real corpus.

## Sensitive signal handling

Safety signals, competitive positioning, and anything touching adverse events are marked for mandatory human review before being shown as actionable. The system routes and prioritises; it does not decide, and it does not communicate externally.

## Retention

The corpus is a local SQLite file committed to this repository for reproducibility. There is no external data store, no telemetry, and no third-party analytics. Text sent to the HuggingFace Inference API during summarisation and chat is limited to retrieved public excerpts and the user's question.
