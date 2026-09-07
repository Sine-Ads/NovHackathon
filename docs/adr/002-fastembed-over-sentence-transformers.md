# 002 · fastembed (ONNX) over sentence-transformers

**Decision.** Embed with `fastembed`, running `qdrant/bge-small-en-v1.5-onnx-q` through ONNX Runtime. 384 dimensions, quantised.

**Rejected.** `sentence-transformers`, the more common choice.

**Why.** `sentence-transformers` pulls PyTorch — roughly 2.5 GB of wheels, CUDA variants, and a platform-specific install that is a frequent source of "works on my machine". `fastembed` is about 90 MB of ONNX Runtime plus a quantised model, installs identically everywhere, and needs no GPU.

These are **not the same library with different packaging.** They ship different model weights and different tokenisation defaults. What carries over is the embedding *interface* and the underlying BGE model family; what does not is exact vector equivalence — embeddings from the two are not interchangeable, and switching requires a full re-index.

**Cost.** A smaller, quantised model retrieves measurably worse than a large one. The model catalogue is narrower. Both were judged acceptable against an install that reliably works.
