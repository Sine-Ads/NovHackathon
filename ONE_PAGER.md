# Haemophilia Intelligence Radar — one page

**Catalyst · Manipal Institute of Technology, Bengaluru**
Ch. Achyuth (lead) · Anagha Ravindran · Nishita Pagaku · Krishna Gunjan · Aditya Alur
Faculty mentor: Dr. Sravani Vemulapalli

---

## The problem

The cost in competitive intelligence is not missing information. It is **late recognition of change**. A competitor programme crossing into Phase 3 is a registry *field change*, not a headline — there is no press release and no article, so there is nothing for a summariser to summarise. A readout that was promised and never delivered produces no document at all.

## What we built

A system that maintains a persistent, structured, versioned state of the haemophilia landscape and **diffs new information against what it already knew**. Output is not "an article mentioned a trial"; it is `NCT0XXXXXXX · Phase 2 → Phase 3`, dated, with the source span that proves it, the function that owns it, and an action with an SLA.

**Running today:** 1,399 records from 4 live public sources · versioned snapshots and a change log · hybrid FTS5 + vector retrieval with Reciprocal Rank Fusion · evidence ranking with full provenance · a deterministic confidence gate · urgency scoring and role routing · a 3-screen Next.js interface · 18 API endpoints · a 15-question golden evaluation suite.

## What makes it different

**1 · It reports absence.** A document saying "primary completion estimated October 2026" is not news — it is a dated obligation. The **Expectation Ledger** registers it as a row with a due date, a watch cadence, and the quote that proves someone promised it. If the event never arrives, that is the signal. *No article is ever written about a readout that did not happen.*

A live query against ClinicalTrials.gov found **134 haemophilia trials with a future primary completion date — every one of them an estimate, not a fact.** They come from a field the ingestor already receives and currently discards. *(Designed, schema frozen; the watch loop has not run.)*

**2 · Absence is auditable.** The Ledger never asks a model whether something happened. Every scheduled probe is logged. The silence card does not claim "nothing happened" — it claims **"we ran 63 searches on these dates against these sources and found nothing"**, and a reviewer can open the log.

**3 · It refuses.** A deterministic gate runs *before* generation: with thin evidence, no model is called at all. The model never writes SQL — it names a whitelisted query, because a generated query can be plausible and wrong. Self-reported confidence can be lowered, never raised. Three of the fifteen golden questions must be refused, and abstention recall gates the suite's exit code.

**4 · It states its limits.** Four of eight connectors returned no data, and the categories they would have fed are never emitted rather than shown as empty tabs. Every record currently sits at "first seen". Both facts are on a slide, not in a footnote.

## Feasibility

No GPU. No internal or patient data. No confidential Novo Nordisk information used or required. Public APIs only, against a fixed allowlist. The corpus is a 4.4 MB file committed to the repository — a reviewer clones and runs. Retrieval, scoring, routing, diffing and the entire Expectation Ledger run with **no model calls at all**; inference is needed only for summaries and chat.

**Next sprint is the differentiator, and it is the cheapest thing left to build:** keep one field the API already returns, add one migration, swap an interval trigger for a date trigger. Roughly 330 lines, no language model.

## What we need

Two short calibration sessions with one or two stakeholders per function — the feedback loop is only demonstrable against real reviewer judgement. Plus confirmation of routing targets, per-function urgency and SLA definitions, priority geographies for HTA weighting, and any sources to add to or remove from the allowlist.

---

`README.md` · `ARCHITECTURE.md` · `RUNBOOK.md` · `EVALUATION.md` · `LIMITATIONS.md` · `docs/EXPECTATION_LEDGER.md` · `docs/adr/` · `docs/RISKS.md` · `docs/DATA_POLICY.md` · `docs/deck/deck.html`
