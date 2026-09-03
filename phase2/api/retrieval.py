"""Hybrid retrieval: keyword and meaning, fused, then evidence-ranked.

    query
      |- FTS5 BM25 ----+
      |- vector cosine +--> RRF fusion --> metadata filters --> evidence ranking

Fusion is Reciprocal Rank Fusion because BM25 scores and cosine similarities are
on incomparable scales; RRF needs only the ranks, so there is nothing to tune.

Search happens over chunks and is then rolled up to items, taking each item's
best chunk. With one chunk per item that rollup is currently an identity
operation — which is the point: real chunking changes ``chunker.py`` alone.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Optional

from api import embed as embed_mod
from api.evidence import Evidence, rank

K_RRF = 60
CANDIDATES = 50

_TOKEN = re.compile(r"[A-Za-z0-9]+")


def sanitize_fts_query(text: str) -> str:
    """Make arbitrary user text safe for FTS5 MATCH.

    Bare input containing quotes, hyphens, colons or the words AND/OR raises
    ``fts5: syntax error``. A stakeholder typing ``factor VIII (severe)`` or an
    NCT identifier must not produce a 500, so every token is quoted and joined
    explicitly.
    """
    tokens = _TOKEN.findall(text or "")
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


def fts_search(conn: sqlite3.Connection, query: str, limit: int = CANDIDATES) -> list[str]:
    """Chunk ids ranked by BM25. Empty list rather than an exception on bad input."""
    match = sanitize_fts_query(query)
    if not match:
        return []
    try:
        rows = conn.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH ? "
            "ORDER BY bm25(chunk_fts) LIMIT ?",
            (match, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r["chunk_id"] for r in rows]


def _hydrate(
    conn: sqlite3.Connection, chunk_ids: list[str]
) -> dict[str, sqlite3.Row]:
    if not chunk_ids:
        return {}
    placeholders = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"""SELECT c.chunk_id, c.text, i.item_id, i.source_name, i.source_id,
                   i.source_url, i.title, i.date_published, i.date_class,
                   i.n_chars, i.is_thin
            FROM chunk c JOIN item i ON i.item_id = c.item_id
            WHERE c.chunk_id IN ({placeholders})""",
        chunk_ids,
    ).fetchall()
    return {r["chunk_id"]: r for r in rows}


def _to_evidence(row: sqlite3.Row) -> Evidence:
    return Evidence(
        chunk_id=row["chunk_id"],
        item_id=row["item_id"],
        source_name=row["source_name"],
        source_id=row["source_id"],
        source_url=row["source_url"],
        title=row["title"],
        date_published=row["date_published"],
        date_class=row["date_class"],
        n_chars=row["n_chars"],
        is_thin=bool(row["is_thin"]),
        text=row["text"],
    )


def hybrid_search(
    conn: sqlite3.Connection,
    index: "embed_mod.VectorIndex",
    query: str,
    k: int = 8,
    sources: Optional[list[str]] = None,
    statuses: Optional[list[str]] = None,
) -> list[Evidence]:
    """Retrieve, fuse, filter, rank. Returns at most ``k`` items."""
    keyword_ids = fts_search(conn, query)
    vector_hits = index.search(embed_mod.embed_query(query), CANDIDATES) if len(index) else []

    scores: dict[str, float] = {}
    fts_rank: dict[str, int] = {}
    vec_rank: dict[str, int] = {}
    vec_score: dict[str, float] = {}

    for position, chunk_id in enumerate(keyword_ids, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (K_RRF + position)
        fts_rank[chunk_id] = position
    for position, (chunk_id, cosine) in enumerate(vector_hits, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (K_RRF + position)
        vec_rank[chunk_id] = position
        vec_score[chunk_id] = cosine

    if not scores:
        return []

    rows = _hydrate(conn, list(scores))

    # Roll chunks up to items: an item scores as its best chunk, and that chunk
    # is the text handed to the model.
    best: dict[str, Evidence] = {}
    for chunk_id, score in scores.items():
        row = rows.get(chunk_id)
        if row is None:
            continue
        item_id = row["item_id"]
        if item_id in best and best[item_id].rrf_score >= score:
            continue
        ev = _to_evidence(row)
        ev.rrf_score = score
        ev.fts_rank = fts_rank.get(chunk_id)
        ev.vec_rank = vec_rank.get(chunk_id)
        ev.vec_score = vec_score.get(chunk_id)
        ev.matched_by = [
            name
            for name, present in (("keyword", ev.fts_rank), ("semantic", ev.vec_rank))
            if present is not None
        ]
        best[item_id] = ev

    candidates = list(best.values())

    # Hard constraints apply after fusion, so a filter narrows the result set
    # without silently reshuffling what ranked first.
    if sources:
        allowed = set(sources)
        candidates = [e for e in candidates if e.source_name in allowed]
    if statuses:
        candidates = _filter_by_status(conn, candidates, statuses)

    return rank(candidates)[:k]


def _filter_by_status(
    conn: sqlite3.Connection, evidence: list[Evidence], statuses: list[str]
) -> list[Evidence]:
    """Trial-status filter, read from the stored metadata JSON."""
    if not evidence:
        return []
    ids = [e.item_id for e in evidence]
    placeholders = ",".join("?" * len(ids))
    wanted = {s.upper() for s in statuses}
    rows = conn.execute(
        f"""SELECT item_id, json_extract(metadata_json, '$.overall_status') AS status
            FROM item WHERE item_id IN ({placeholders})""",
        ids,
    ).fetchall()
    keep = {r["item_id"] for r in rows if (r["status"] or "").upper() in wanted}
    return [e for e in evidence if e.item_id in keep]


def similar_items(
    conn: sqlite3.Connection,
    index: "embed_mod.VectorIndex",
    item_id: str,
    k: int = 6,
) -> list[Evidence]:
    """Nearest neighbours of an item, evidence-ranked.

    Serves both the 'Related coverage' panel and the neighbour context the
    per-item chatbot is allowed to see.
    """
    hits = index.similar_to_item(item_id, limit=k * 3)
    if not hits:
        return []
    rows = _hydrate(conn, [chunk_id for chunk_id, _ in hits])

    best: dict[str, Evidence] = {}
    for position, (chunk_id, cosine) in enumerate(hits, start=1):
        row = rows.get(chunk_id)
        if row is None or row["item_id"] == item_id:
            continue
        if row["item_id"] in best:
            continue
        ev = _to_evidence(row)
        # Neighbours have no keyword list to fuse with, so the single ranked
        # list feeds RRF on its own; relative order is what matters here.
        ev.rrf_score = 1.0 / (K_RRF + position)
        ev.vec_rank = position
        ev.vec_score = cosine
        ev.matched_by = ["semantic"]
        best[row["item_id"]] = ev

    return rank(list(best.values()))[:k]
