# 001 · SQLite + FTS5 over PostgreSQL + pgvector

**Decision.** Store everything in SQLite, using FTS5 for keyword search and an in-memory numpy matrix for vector search.

**Rejected.** PostgreSQL with the pgvector extension — the choice named in the original concept note.

**Why.** The deciding constraint was not performance, it was *reproducibility by a stranger*. A judge clones this repository and runs it. With Postgres that means installing a server, creating a role and a database, enabling an extension, and restoring a dump — four opportunities to fail before seeing anything. With SQLite the corpus is a 4.4 MB file committed to the repo, and the first command that touches it works.

At 1,399 records the performance difference is unmeasurable. FTS5 BM25 is a mature implementation, and 1,399 × 384 floats is 2 MB of RAM.

**Cost.** No concurrent writers. No horizontal scaling. Vector search is a full scan — linear in corpus size, which stops being acceptable somewhere around 10⁵ records. All three are real, and none of them bind at this size. A production deployment would migrate; the schema is deliberately portable.
