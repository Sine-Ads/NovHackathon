# 003 · Phase 1 frozen, opened read-only

**Decision.** Phase 2 modifies no file under `data-ingestion-system/` or `llm_1/`, and opens the Phase 1 database with SQLite's `mode=ro` URI flag. All Phase 2 writes go to `phase2/data/phase2.db`.

**Rejected.** Adding Phase 2's tables to the Phase 1 database and treating the whole thing as one schema.

**Why.** Three reasons, in order of weight.

The evidence base must not be corruptible by the layer that reasons over it. In a system whose entire value proposition is provenance, a Phase 2 bug that mutates a `raw_items` row would invalidate every claim the system has ever made, silently and unrecoverably.

Second, the boundary had to be *enforced* rather than agreed. A team convention holds until someone is in a hurry at 2 a.m. `mode=ro` raises `OperationalError` instead.

Third, it decouples the work. Phase 1 can be re-ingested, migrated or replaced without coordinating with Phase 2; deleting the sidecar resets all derived state and loses nothing original.

**Cost.** Derived state is duplicated — item rows exist in both databases. Cross-database joins are done in Python rather than SQL. The `classifications` table is the one exception, read live rather than indexed, so re-running the classifier is visible immediately.
