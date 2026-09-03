"""Read-only access to the ``classifications`` table.

Phase 1 gained a classifier (commit 626e274) that writes one verdict per
``raw_items.id``. The contract is defined in ``FRONTEND_INTEGRATION.md``:

    category    proven_right | proven_false | proven_false_but_useful |
                still_working_on, or NULL when the attempt failed
    method      rule | llm
    status      classified | failed
    reason      failure detail, NULL on success

Two rules from that document are enforced here rather than left to callers:

  1. "Failed records should remain visible to operators with status 'failed'
     and their reason, but should not be presented as a category." So a failed
     row is returned, but never counted in a category and never offered as a
     filter value.
  2. Classifications change independently of ``raw_items`` — the classifier can
     be re-run at any time. They are therefore read live from the source
     database on each request rather than copied into the sidecar index, where
     they would silently go stale (the content hash that drives reindexing
     covers the item text, not its verdict).

The table may not exist: it arrives with alembic revision 002, and a database
still on 001 is entirely valid. Every function here degrades to "no data"
rather than raising, so the radar runs identically with or without it.
"""
from __future__ import annotations

import sqlite3
import threading
from typing import Any, Iterable, Optional

# The four verdicts, in the order a stakeholder reads them: settled-good,
# settled-bad, salvageable, still-open.
CATEGORIES = (
    "proven_right",
    "proven_false_but_useful",
    "proven_false",
    "still_working_on",
)

CATEGORY_LABELS = {
    "proven_right": "Proven right",
    "proven_false": "Proven false",
    "proven_false_but_useful": "Proven false, still useful",
    "still_working_on": "Still working on",
}

# Shown to the assistants so a verdict is never over-read. The classifier
# assigns these from publication type, retraction flag and citation count — not
# from a full appraisal of the evidence.
CATEGORY_MEANINGS = {
    "proven_right": "independently confirmed (meta-analysis, replication, or strong RCT)",
    "proven_false": "contradicted, retracted, or the trial failed or was terminated",
    "proven_false_but_useful": "retracted or failed, but the data has been cited or reused",
    "still_working_on": "preprint, early-phase, or recruiting with no established result yet",
}

_available: Optional[bool] = None
_lock = threading.Lock()


def available(conn: sqlite3.Connection, recheck: bool = False) -> bool:
    """Whether the classifications table exists in the source database.

    Cached, because it is checked on nearly every request. ``recheck=True``
    clears the cache — used after a teammate runs ``alembic upgrade head`` so a
    running API picks the table up without a restart.
    """
    global _available
    if recheck:
        with _lock:
            _available = None
    if _available is None:
        with _lock:
            if _available is None:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='classifications'"
                ).fetchone()
                _available = row is not None
    return _available


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    status = row["status"] or "classified"
    failed = status == "failed" or not row["category"]
    category = None if failed else row["category"]
    return {
        "category": category,
        "category_label": CATEGORY_LABELS.get(category) if category else None,
        "justification": row["justification"],
        "method": row["method"],
        "status": "failed" if failed else status,
        "reason": row["reason"],
        "classified_at": row["classified_at"],
    }


def for_items(
    conn: sqlite3.Connection, item_ids: Iterable[str]
) -> dict[str, dict[str, Any]]:
    """Verdicts for the given raw_item ids, keyed by id. Missing ids are absent."""
    ids = [i for i in item_ids if i]
    if not ids or not available(conn):
        return {}
    out: dict[str, dict[str, Any]] = {}
    # Chunked to stay under SQLite's variable limit if the caller passes many.
    for start in range(0, len(ids), 500):
        batch = ids[start : start + 500]
        placeholders = ",".join("?" * len(batch))
        rows = conn.execute(
            f"""SELECT raw_item_id, category, justification, method, status,
                       reason, classified_at
                FROM classifications WHERE raw_item_id IN ({placeholders})""",
            batch,
        ).fetchall()
        for row in rows:
            out[row["raw_item_id"]] = _row_to_dict(row)
    return out


def for_item(conn: sqlite3.Connection, item_id: str) -> Optional[dict[str, Any]]:
    return for_items(conn, [item_id]).get(item_id)


def ids_in_category(conn: sqlite3.Connection, category: str) -> set[str]:
    """raw_item ids carrying a given verdict.

    ``failed`` is accepted as a pseudo-category so operators can review what the
    classifier could not handle — the integration document asks for those to
    stay visible without being presented as a real category.
    """
    if not available(conn):
        return set()
    if category == "failed":
        rows = conn.execute(
            "SELECT raw_item_id FROM classifications "
            "WHERE status = 'failed' OR category IS NULL"
        ).fetchall()
    elif category in CATEGORIES:
        rows = conn.execute(
            "SELECT raw_item_id FROM classifications "
            "WHERE category = ? AND status != 'failed'",
            (category,),
        ).fetchall()
    else:
        return set()
    return {r["raw_item_id"] for r in rows}


def counts(conn: sqlite3.Connection) -> dict[str, Any]:
    """Verdict distribution, plus coverage against the whole corpus."""
    if not available(conn):
        return {
            "available": False,
            "classified": 0,
            "failed": 0,
            "unclassified": 0,
            "by_category": {},
            "by_method": {},
        }

    by_category: dict[str, int] = {}
    for row in conn.execute(
        "SELECT category, count(*) n FROM classifications "
        "WHERE status != 'failed' AND category IS NOT NULL GROUP BY 1"
    ):
        by_category[row["category"]] = row["n"]

    by_method = {
        row["method"] or "unknown": row["n"]
        for row in conn.execute(
            "SELECT method, count(*) n FROM classifications "
            "WHERE status != 'failed' GROUP BY 1"
        )
    }

    failed = conn.execute(
        "SELECT count(*) FROM classifications WHERE status = 'failed' OR category IS NULL"
    ).fetchone()[0]
    total_rows = conn.execute("SELECT count(*) FROM classifications").fetchone()[0]
    corpus = conn.execute("SELECT count(*) FROM raw_items WHERE is_active = 1").fetchone()[0]

    return {
        "available": True,
        "classified": total_rows - failed,
        "failed": failed,
        "unclassified": max(0, corpus - total_rows),
        "corpus": corpus,
        "by_category": {c: by_category.get(c, 0) for c in CATEGORIES if by_category.get(c)},
        "by_method": by_method,
    }


def describe(verdict: Optional[dict[str, Any]]) -> str:
    """One line for an LLM prompt, or empty when there is nothing to say."""
    if not verdict:
        return ""
    if verdict["status"] == "failed":
        return "Classification: attempted but failed; treat this record as unclassified."
    category = verdict["category"]
    if not category:
        return ""
    meaning = CATEGORY_MEANINGS.get(category, "")
    line = f"Classification: {CATEGORY_LABELS.get(category, category)} — {meaning}"
    if verdict.get("method"):
        # The distinction matters: a rule verdict is deterministic metadata, an
        # LLM verdict is a judgement the assistant should not treat as fact.
        line += f" (assigned by {verdict['method']})"
    return line
