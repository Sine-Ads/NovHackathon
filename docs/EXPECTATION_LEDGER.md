# The Expectation Ledger

**Status: designed, schema frozen, not yet running. Seeded from real corpus data.**

This document specifies the capability that separates the Radar from every summariser: it watches for events that were *promised* and reports the ones that never arrive.

---

## 1. The idea

A document that says

> "primary completion estimated **October 2026**"

is not news. It is a **dated obligation**. Something is supposed to happen, on or around a date, and somebody has said so on the record.

Today every system in this space treats that sentence as text to be indexed. It is not text. It is a row in a ledger with a due date, an owner, and a quote that proves it was promised.

Two things can then happen:

- **The event arrives.** The Radar already knows what to compare it against, so it produces a confirmed state transition rather than another article.
- **The event does not arrive.** *This is the signal.* A delayed readout, a slipped filing, a completion date that quietly moves — these are among the most decision-relevant events in competitive intelligence, and **no article is ever written about them.** A summariser cannot surface a non-event, because there is no document to summarise.

## 2. Why this is credible here, not hand-waving

The corpus already contains the raw material, and the system already half-recognises it.

**The promise field is in API responses we already fetch and currently discard.** `app/ingestors/clinical_trials.py` requests the full study record from ClinicalTrials.gov v2 with no field mask, so `statusModule.primaryCompletionDateStruct` arrives in every response. The ingestor reads `startDateStruct` and drops the rest.

A live count against that same endpoint, same query, on 2026-09-07:

| | |
|---|---|
| Haemophilia studies matched | 992 |
| Carrying a primary completion date | 946 |
| **Dated in the future** | **134** |
| Of those, typed `ESTIMATED` rather than `ACTUAL` | **134 — every one** |

**134 open commitments the Radar would be watching today.** Not a projection. A count. They include `NCT07653139` (Novo Nordisk A/S, 2026-10-26), `NCT06738485` (CSL Behring, 2026-10-26), `NCT03588299` (Bayer, 2026-09-15) and `NCT06550882` (Takeda, 2026-09-30).

**The system already detects forward-dated records — and deliberately ignores them.** `phase2/api/evidence.py:100-121` holds trials recency-neutral precisely because ClinicalTrials.gov stores a date the study has not reached:

```python
# ClinicalTrials.gov stores a study *start* date — 9 rows are dated into 2027 —
# so trials are held neutral rather than rewarded for a date they have not reached.
if date_class not in ("publication", "filing") or not date_published:
    return 1.00
```

That guard is the detector. It identifies exactly the records that carry a future date and then throws the information away. The Expectation Ledger is what that branch should feed.

**The scheduler column already exists and has never been written.** `data-ingestion-system/app/database.py:156` declares `scheduling_metadata.next_scheduled_run`. It is documented, migrated, and `NULL` for all 8 ingestors, because the scheduler only ever uses fixed `IntervalTrigger`s. The ledger is what makes that column mean something.

## 3. Schema

```sql
CREATE TABLE expectation (
  id               TEXT PRIMARY KEY,
  source_item_id   TEXT NOT NULL,   -- the document that made the promise
  entity           TEXT NOT NULL,   -- sponsor / company
  asset            TEXT,            -- programme or product, where identifiable
  event_type       TEXT NOT NULL,   -- readout | filing | approval |
                                    -- enrolment_complete | chmp_opinion | pdufa
  window_start     TEXT NOT NULL,   -- ISO date
  window_end       TEXT NOT NULL,   -- widened from `precision`, see below
  precision        TEXT NOT NULL,   -- day | month | quarter | half | year
  confidence       REAL NOT NULL,
  quote_span       TEXT NOT NULL,   -- exact supporting text. No span, no row.
  source_url       TEXT NOT NULL,
  status           TEXT NOT NULL,   -- OPEN | WATCHING | MET | MISSED
                                    -- | RETRACTED | SUPERSEDED
  next_check_at    TEXT,            -- drives the scheduler
  resolved_item_id TEXT,            -- the document that satisfied it
  resolved_at      TEXT,
  created_at       TEXT NOT NULL,
  FOREIGN KEY (source_item_id) REFERENCES raw_items(id)
);

CREATE TABLE watch_probe (          -- provenance for a non-event
  id             TEXT PRIMARY KEY,
  expectation_id TEXT NOT NULL,
  ran_at         TEXT NOT NULL,
  query          TEXT NOT NULL,     -- the exact query issued
  sources        TEXT NOT NULL,     -- which connectors were asked
  n_candidates   INTEGER NOT NULL,
  matched        INTEGER NOT NULL,
  FOREIGN KEY (expectation_id) REFERENCES expectation(id)
);
```

**`quote_span` is mandatory.** An expectation with no exact supporting text is not written. This is the same rule the retrieval layer already enforces on claims: provenance or abstention, never generation.

**Date precision widens the window rather than guessing a day.** "Q3 2027" becomes `window_start = 2027-07-01`, `window_end = 2027-09-30`, `precision = quarter`. The system never pretends to know a day it was not told.

## 4. Scheduler contract

One expectation, four phases, driven entirely by `next_check_at`.

| Phase | Condition | Cadence | Action |
|---|---|---|---|
| **Dormant** | `now < window_start − 14d` | weekly | Cheap existence check; catch early arrivals and retractions |
| **Approach** | `window_start − 14d ≤ now ≤ window_end` | daily | Targeted query built from `entity + asset + event_type` |
| **Burst** | `window_end < now ≤ window_end + grace` | every 6 h | The window has closed; the event is now late |
| **Resolve** | `now > window_end + grace` | — | Emit **silence signal**, set `status = MISSED` |

Grace period by event type — how late is late depends on what was promised:

| `event_type` | Grace |
|---|---|
| `readout` | 30 d |
| `enrolment_complete` | 30 d |
| `chmp_opinion` | 30 d |
| `filing` | 45 d |
| `approval` | 60 d |

**Resolution.** Candidates returned by each probe are matched against the expectation on `(entity, asset, event_type)` — entity-link equality plus embedding similarity above threshold, reusing `phase2/api/retrieval.py` rather than a second matcher. A match sets `status = MET`, records `resolved_item_id`, and emits an ordinary change signal through the existing `item_change` path.

**Supersession.** If the source document is re-ingested with a later date, the old row becomes `SUPERSEDED` and a new one opens. A completion date that slips twice is itself a strong signal, and the ledger preserves that history rather than overwriting it.

## 5. Why the silence signal is auditable

This is the part that matters in a regulated setting.

Asserting that something did not happen is a claim about absence, and absence is exactly what a language model will confabulate. So the ledger never asks a model. **Every probe is logged whether it matches or not.** The `watch_probe` rows *are* the evidence:

> **SILENCE · HIGH · Clinical Development**
>
> **What changed** — Expected `readout` for NCT06550882 (Takeda) did not arrive.
> Promised window 2026-09-30, grace 30 d, elapsed 41 d.
>
> **Why it matters** — A slipped primary completion in a competing extended-half-life
> programme moves the comparative-data timeline in a reference market.
>
> **Who reviews** — Clinical Development (primary) · Market Access (informed)
> **Action** — `HTA_WATCH_ITEM` · owner Clinical Development · SLA 14 d
>
> **Evidence** — original commitment: *"Estimated primary completion date: 2026-09-30"*
> (ClinicalTrials.gov, retrieved 2026-09-01) · **63 probes across 4 sources between
> 2026-09-16 and 2026-11-10, 0 matches** — [see probe log]

The claim is not "we believe nothing happened". The claim is **"we ran 63 searches on these dates against these sources and found nothing"**, and the log is inspectable. A reviewer can disagree with the conclusion by pointing at a source the probe did not cover — which is a productive argument, and exactly the kind the calibration loop is built to absorb.

## 6. Implementation cost

Deliberately small, because it reuses what exists.

| Change | Where | Size |
|---|---|---|
| Keep `primaryCompletionDateStruct` when parsing studies | `app/ingestors/clinical_trials.py` | ~4 lines |
| Migration `003_expectations` | `data-ingestion-system/migrations/versions/` | new file, 2 tables |
| Extraction pass over forward-dated records | new `app/expectations.py` | ~120 lines; the CT.gov path is pure field-mapping, no LLM |
| Swap `IntervalTrigger` for `DateTrigger` on ledger jobs | `app/scheduler.py:37` | ~20 lines |
| Probe runner + matcher | new; calls `phase2/api/retrieval.py` | ~150 lines |
| Silence card rendering | `phase2/api/signals.py` — a change event with a null right-hand side | ~40 lines |

The 134 ClinicalTrials.gov expectations need **no language model at all** — the date, the sponsor, the trial and the event type are structured fields. An LLM is only needed to extend the ledger to prose sources (press releases, investor decks, congress abstracts), which is the second sprint, not the first.

## 7. What this specification does not claim

- The watch loop has **not been run**. No probe has been issued and no silence signal has been emitted.
- The 134 count is a live query against ClinicalTrials.gov, not an output of this system.
- Prose extraction of expectations ("topline data expected in the second half") is designed but unvalidated; only the structured registry path is field-mapping and therefore reliable today.
- Matching thresholds are reasoned from the existing retrieval configuration, not tuned against labelled resolution data — because no resolution data exists until the loop has run for a full window.

The honest summary: **the ledger is specified to implementation readiness and seeded with real, verifiable data, and it has not executed.**
