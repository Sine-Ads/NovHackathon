# 006 · A deterministic confidence gate runs before generation

**Decision.** Evidence sufficiency is decided in code before any LLM call. With no evidence, evidence below `MIN_EVIDENCE`, or nothing but stubs, **no call is made** and a templated reply names what was missing. After generation, self-reported confidence may be lowered but never raised.

**Rejected.** Instructing the model to say "I don't know" when unsure.

**Why.** A model asked to assess its own confidence is being asked to be its own auditor, and it is bad at it in a specific direction — it under-refuses. Prompt-based abstention fails exactly when the corpus is thinnest, which is when refusal matters most.

Moving the decision before generation also makes it *free* and *deterministic*: the same query with the same index always produces the same refusal, and a refused query costs no tokens.

The asymmetry — self-report can lower confidence, never raise it — closes the remaining hole. A model that has satisfied the deterministic gate may still recognise it is synthesising rather than citing, and that admission is honoured; the reverse claim is not.

**Cost.** The system refuses some questions a knowledgeable human could answer from general knowledge. Three golden questions test precisely this, and abstention recall gates the suite's exit code.
