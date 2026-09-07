# 005 · Tool round-trips capped at exactly one

**Decision.** The chat loop permits one tool call and one continuation. Never two. Enforced at `phase2/api/chat.py:234`.

**Rejected.** An open agent loop iterating until the model stops calling tools.

**Why.** An unbounded loop has unbounded latency and unbounded cost, and its failure mode under uncertainty is to keep calling tools — exactly when the honest answer is "the corpus cannot support this". A cap converts that failure into an abstention, which is the behaviour this system is built around.

One round-trip covers the observed question distribution: retrieve, or aggregate, or both in parallel. Chained aggregates were not needed by any of the 15 golden questions.

**Cost.** Genuine multi-hop questions — "which sponsor has the most terminated trials, and what were their stated reasons" — cannot be answered. This is a known, documented gap rather than a silent truncation.
