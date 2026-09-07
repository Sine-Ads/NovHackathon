# 008 · ClinicalTrials.gov records are held recency-neutral

**Decision.** The recency multiplier applies only where `date_class` is `publication` or `filing`. Trials return a flat 1.00. Implemented at `phase2/api/evidence.py:100-121`.

**Rejected.** Applying recency uniformly using whatever date each source provides.

**Why.** The ingestor stores ClinicalTrials.gov's `startDateStruct` — a study *start* date, not a publication event. Nine records in the corpus are dated into 2027. Under a uniform recency rule those would be the *most* recent records in the system and would outrank everything, on the strength of a date they have not reached.

The general principle: a date is not a date. Different sources emit dates with different semantics, and the system labels them differently in the UI for the same reason — `Published`, `Study start`, `Filed`, `Date unknown`.

**Cost.** A genuinely recent trial gets no recency boost. Given the ±10% band is narrower than typical gaps between adjacent RRF ranks, the loss is small.

**Note.** This decision identifies exactly the records that carry a future date, and then discards that information. [`../EXPECTATION_LEDGER.md`](../EXPECTATION_LEDGER.md) is the argument that this branch should instead feed a watch registry.
