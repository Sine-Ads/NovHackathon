"""Phase 2's own database: schema and access.

Everything Phase 2 writes lands here. The Phase 1 database stays byte-identical.

The schema is keyed on ``chunk_id`` rather than ``item_id`` even though the
current corpus produces exactly one chunk per item (average item is ~1.2k
characters). That indirection costs nothing today and means the arrival of long
documents — full SEC filing text, full-text papers — is confined to
``chunker.py`` instead of rippling through retrieval, fusion and the API.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from api.config import sidecar_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS item (
  item_id        TEXT PRIMARY KEY,
  source_name    TEXT NOT NULL,
  source_id      TEXT NOT NULL,
  source_url     TEXT,
  title          TEXT,
  date_published TEXT,
  date_ingested  TEXT NOT NULL,
  metadata_json  TEXT,
  n_chars        INTEGER NOT NULL,
  is_thin        INTEGER NOT NULL DEFAULT 0,
  date_class     TEXT NOT NULL,
  content_hash   TEXT NOT NULL,
  indexed_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_item_source ON item(source_name);
CREATE INDEX IF NOT EXISTS ix_item_date ON item(date_published);

CREATE TABLE IF NOT EXISTS chunk (
  chunk_id    TEXT PRIMARY KEY,
  item_id     TEXT NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  text        TEXT NOT NULL,
  n_chars     INTEGER NOT NULL,
  UNIQUE(item_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS ix_chunk_item ON chunk(item_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
  chunk_id UNINDEXED, item_id UNINDEXED, title, text,
  tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS embedding (
  chunk_id TEXT PRIMARY KEY REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  item_id  TEXT NOT NULL,
  model    TEXT NOT NULL,
  dim      INTEGER NOT NULL,
  vec      BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_embedding_item ON embedding(item_id);

CREATE TABLE IF NOT EXISTS summary_cache (
  item_id      TEXT PRIMARY KEY,
  model        TEXT NOT NULL,
  summary      TEXT,
  key_facts    TEXT,
  why_matters  TEXT,
  functions    TEXT,
  confidence   TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_thread (
  thread_id  TEXT PRIMARY KEY,
  scope      TEXT NOT NULL CHECK(scope IN ('item','global')),
  item_id    TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_message (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id  TEXT NOT NULL REFERENCES chat_thread(thread_id) ON DELETE CASCADE,
  role       TEXT NOT NULL CHECK(role IN ('user','assistant')),
  content    TEXT NOT NULL,
  confidence TEXT,
  evidence   TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chat_thread ON chat_message(thread_id, id);

CREATE TABLE IF NOT EXISTS landscape (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  computed_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    """Open the sidecar database read-write, with the schema ensured."""
    conn = sqlite3.connect(sidecar_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def drop_all(conn: sqlite3.Connection) -> None:
    """Tear the index down for a --rebuild. Never touches the Phase 1 database."""
    for table in (
        "chunk_fts",
        "embedding",
        "chunk",
        "item",
        "summary_cache",
        "landscape",
    ):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    conn.executescript(SCHEMA)
    conn.commit()


# --------------------------------------------------------------------------
# Index writes
# --------------------------------------------------------------------------


def existing_hashes(conn: sqlite3.Connection) -> dict[str, str]:
    """item_id -> content_hash, for skipping unchanged rows on reindex."""
    return {
        row["item_id"]: row["content_hash"]
        for row in conn.execute("SELECT item_id, content_hash FROM item")
    }


def upsert_item(conn: sqlite3.Connection, **fields: Any) -> None:
    fields["indexed_at"] = now_iso()
    columns = ", ".join(fields)
    placeholders = ", ".join("?" * len(fields))
    updates = ", ".join(f"{c}=excluded.{c}" for c in fields if c != "item_id")
    conn.execute(
        f"INSERT INTO item ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(item_id) DO UPDATE SET {updates}",
        tuple(fields.values()),
    )


def replace_chunks(
    conn: sqlite3.Connection, item_id: str, title: Optional[str], chunks: list[tuple[str, str]]
) -> None:
    """Replace every chunk for an item. ``chunks`` is a list of (chunk_id, text)."""
    conn.execute("DELETE FROM chunk_fts WHERE item_id = ?", (item_id,))
    conn.execute("DELETE FROM chunk WHERE item_id = ?", (item_id,))
    for index, (chunk_id, text) in enumerate(chunks):
        conn.execute(
            "INSERT INTO chunk (chunk_id, item_id, chunk_index, text, n_chars) "
            "VALUES (?, ?, ?, ?, ?)",
            (chunk_id, item_id, index, text, len(text)),
        )
        conn.execute(
            "INSERT INTO chunk_fts (chunk_id, item_id, title, text) VALUES (?, ?, ?, ?)",
            (chunk_id, item_id, title or "", text),
        )


def delete_items(conn: sqlite3.Connection, item_ids: Iterable[str]) -> int:
    ids = list(item_ids)
    if not ids:
        return 0
    for item_id in ids:
        conn.execute("DELETE FROM chunk_fts WHERE item_id = ?", (item_id,))
        conn.execute("DELETE FROM embedding WHERE item_id = ?", (item_id,))
        conn.execute("DELETE FROM chunk WHERE item_id = ?", (item_id,))
        conn.execute("DELETE FROM item WHERE item_id = ?", (item_id,))
    return len(ids)


def store_embeddings(
    conn: sqlite3.Connection, rows: list[tuple[str, str, str, int, bytes]]
) -> None:
    """rows: (chunk_id, item_id, model, dim, vec_bytes)."""
    conn.executemany(
        "INSERT INTO embedding (chunk_id, item_id, model, dim, vec) VALUES (?,?,?,?,?) "
        "ON CONFLICT(chunk_id) DO UPDATE SET "
        "item_id=excluded.item_id, model=excluded.model, dim=excluded.dim, vec=excluded.vec",
        rows,
    )


def chunks_missing_embeddings(conn: sqlite3.Connection, model: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT c.chunk_id, c.item_id, c.text
           FROM chunk c
           LEFT JOIN embedding e ON e.chunk_id = c.chunk_id AND e.model = ?
           WHERE e.chunk_id IS NULL""",
        (model,),
    ).fetchall()


# --------------------------------------------------------------------------
# Summary cache
# --------------------------------------------------------------------------


def get_summary(conn: sqlite3.Connection, item_id: str, content_hash: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM summary_cache WHERE item_id = ? AND content_hash = ?",
        (item_id, content_hash),
    ).fetchone()
    if not row:
        return None
    return {
        "summary": row["summary"],
        "why_matters": row["why_matters"],
        "key_facts": json.loads(row["key_facts"] or "[]"),
        "functions": json.loads(row["functions"] or "[]"),
        "confidence": row["confidence"],
    }


def put_summary(
    conn: sqlite3.Connection, item_id: str, content_hash: str, model: str, payload: dict
) -> None:
    conn.execute(
        """INSERT INTO summary_cache
             (item_id, model, summary, key_facts, why_matters, functions,
              confidence, content_hash, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(item_id) DO UPDATE SET
             model=excluded.model, summary=excluded.summary,
             key_facts=excluded.key_facts, why_matters=excluded.why_matters,
             functions=excluded.functions, confidence=excluded.confidence,
             content_hash=excluded.content_hash, created_at=excluded.created_at""",
        (
            item_id,
            model,
            payload.get("summary"),
            json.dumps(payload.get("key_facts", [])),
            payload.get("why_matters"),
            json.dumps(payload.get("functions", [])),
            payload.get("confidence", "abstain"),
            content_hash,
            now_iso(),
        ),
    )
    conn.commit()


# --------------------------------------------------------------------------
# Landscape cache
# --------------------------------------------------------------------------


def get_landscape(conn: sqlite3.Connection, key: str = "main") -> Optional[dict]:
    row = conn.execute("SELECT value FROM landscape WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def put_landscape(conn: sqlite3.Connection, value: dict, key: str = "main") -> None:
    conn.execute(
        "INSERT INTO landscape (key, value, computed_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, computed_at=excluded.computed_at",
        (key, json.dumps(value), now_iso()),
    )
    conn.commit()


# --------------------------------------------------------------------------
# Chat persistence
# --------------------------------------------------------------------------


def ensure_thread(
    conn: sqlite3.Connection, thread_id: str, scope: str, item_id: Optional[str]
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO chat_thread (thread_id, scope, item_id, created_at) "
        "VALUES (?,?,?,?)",
        (thread_id, scope, item_id, now_iso()),
    )
    conn.commit()


def add_message(
    conn: sqlite3.Connection,
    thread_id: str,
    role: str,
    content: str,
    confidence: Optional[str] = None,
    evidence: Optional[list] = None,
) -> None:
    conn.execute(
        "INSERT INTO chat_message (thread_id, role, content, confidence, evidence, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (
            thread_id,
            role,
            content,
            confidence,
            json.dumps(evidence) if evidence is not None else None,
            now_iso(),
        ),
    )
    conn.commit()


def get_history(conn: sqlite3.Connection, thread_id: str, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT role, content, confidence, evidence, created_at FROM chat_message "
        "WHERE thread_id = ? ORDER BY id DESC LIMIT ?",
        (thread_id, limit),
    ).fetchall()
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "confidence": r["confidence"],
            "evidence": json.loads(r["evidence"]) if r["evidence"] else [],
            "created_at": r["created_at"],
        }
        for r in reversed(rows)
    ]


def index_stats(conn: sqlite3.Connection) -> dict:
    def count(table: str) -> int:
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])

    return {
        "items": count("item"),
        "chunks": count("chunk"),
        "embeddings": count("embedding"),
        "fts_rows": count("chunk_fts"),
        "summaries_cached": count("summary_cache"),
    }
