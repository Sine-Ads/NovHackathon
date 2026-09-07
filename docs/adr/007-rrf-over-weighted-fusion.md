# 007 · Reciprocal Rank Fusion, not weighted score fusion

**Decision.** Fuse BM25 and vector results using only their ranks, via Reciprocal Rank Fusion.

**Rejected.** Normalising both scores and combining them with a tuned weight.

**Why.** BM25 scores and cosine similarities live on incomparable scales. BM25 is unbounded and corpus-dependent; cosine is bounded in [-1, 1]. Any normalisation imposes an arbitrary mapping, and the resulting weight is a hyperparameter that needs a labelled tuning set to fit — which did not exist at the time this was written, and would have been fitted to 15 questions if it had.

RRF uses ordinal information only. There is nothing to tune, nothing to overfit, and it degrades gracefully when one retriever returns nothing.

**Cost.** Score magnitude is discarded, so an overwhelmingly strong keyword match ranks the same as a marginal one at the same position. In practice evidence ranking recovers some of this through completeness and recency multipliers.
