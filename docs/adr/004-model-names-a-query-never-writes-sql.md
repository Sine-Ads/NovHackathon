# 004 · The model names a whitelisted query; it never writes SQL

**Decision.** Aggregate questions are answered from a fixed registry of parameterised queries (`phase2/api/aggregates.py`). The model selects one by name and supplies arguments. It never emits SQL, and never sees a database connection.

**Rejected.** Text-to-SQL, the standard approach.

**Why.** Two failures that text-to-SQL cannot rule out, both fatal here.

A generated query can be *plausible and wrong* — counting the wrong join, missing a `DISTINCT`, silently dropping NULLs — and return a confident number no reviewer can audit without reading the SQL. In a decision-support tool for a regulated industry, a wrong number is worse than a refusal.

And a generated query is an injection surface against the corpus that every claim depends on.

Retrieval also physically cannot answer counting questions: top-k sees eight documents and cannot know how many of 1,399 trials are recruiting. So a deterministic path was needed regardless.

**Cost.** Only anticipated aggregates are answerable. A novel counting question fails rather than being improvised — which is the intended trade, and the gap is visible in the eval suite rather than hidden.
