"""Read-only access to the Phase 1 ``raw_items`` table.

Phase 2 deliberately does not import ``app.database`` from the ingestion
package. Doing so would pull sqlalchemy, apscheduler, alembic, asyncpg and
tenacity into this environment for the sake of one ORM class, and every call
site would then have to remember to pass ``db_url=`` to avoid the cwd-relative
settings singleton. Reading the table with parameterised SQL keeps Phase 2's
dependency tree disjoint and makes the wrong-database failure structurally
impossible instead of merely avoided.

``raw_items`` is eight stable columns; ``assert_schema`` catches drift.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from api.config import read_only_uri, source_db_path

EXPECTED_COLUMNS = {
    "id",
    "source_name",
    "source_id",
    "source_url",
    "title",
    "raw_content",
    "date_published",
    "date_ingested",
    "metadata",
    "is_active",
}

# What ``date_published`` actually means, per source. ClinicalTrials.gov stores a
# study *start* date (9 rows are dated into 2027); PubMed/arXiv store publication
# dates; SEC stores a filing date. Ranking and UI labelling both depend on this
# distinction, so it is resolved once here rather than guessed downstream.
DATE_CLASS_BY_SOURCE = {
    "ClinicalTrials.gov": "trial_start",
    "WHO ICTRP": "trial_start",
    "PubMed (NCBI)": "publication",
    "arXiv": "publication",
    "medRxiv": "publication",
    "SEC EDGAR": "filing",
    "USPTO Patents": "filing",
    "OpenFDA": "filing",
}


@dataclass
class SourceItem:
    """One row of ``raw_items``, with metadata already decoded."""

    item_id: str
    source_name: str
    source_id: str
    source_url: Optional[str]
    title: Optional[str]
    raw_content: Optional[str]
    date_published: Optional[str]
    date_ingested: str
    metadata: dict[str, Any]
    is_active: bool

    @property
    def date_class(self) -> str:
        if not self.date_published:
            return "unknown"
        return DATE_CLASS_BY_SOURCE.get(self.source_name, "unknown")


def connect() -> sqlite3.Connection:
    """Open the Phase 1 database read-only."""
    conn = sqlite3.connect(read_only_uri(), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def assert_schema(conn: sqlite3.Connection) -> None:
    """Fail loudly if ``raw_items`` no longer looks the way Phase 2 expects."""
    rows = conn.execute("PRAGMA table_info(raw_items)").fetchall()
    if not rows:
        raise RuntimeError(
            f"No raw_items table in {source_db_path()} — wrong database file?"
        )
    columns = {row[1] for row in rows}
    missing = EXPECTED_COLUMNS - columns
    if missing:
        raise RuntimeError(f"raw_items is missing expected columns: {sorted(missing)}")


def _row_to_item(row: sqlite3.Row) -> SourceItem:
    try:
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    return SourceItem(
        item_id=row["id"],
        source_name=row["source_name"],
        source_id=row["source_id"],
        source_url=row["source_url"],
        title=row["title"],
        raw_content=row["raw_content"],
        date_published=row["date_published"],
        date_ingested=row["date_ingested"],
        metadata=metadata if isinstance(metadata, dict) else {},
        is_active=bool(row["is_active"]),
    )


_SELECT = """
    SELECT id, source_name, source_id, source_url, title, raw_content,
           date_published, date_ingested, metadata, is_active
    FROM raw_items
"""


def iter_items(conn: sqlite3.Connection, active_only: bool = True) -> Iterator[SourceItem]:
    """Stream every row. The corpus is ~1,400 rows, so a full scan is cheap."""
    sql = _SELECT + ("WHERE is_active = 1" if active_only else "")
    for row in conn.execute(sql):
        yield _row_to_item(row)


def get_item(conn: sqlite3.Connection, item_id: str) -> Optional[SourceItem]:
    row = conn.execute(_SELECT + "WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def get_items(conn: sqlite3.Connection, item_ids: list[str]) -> dict[str, SourceItem]:
    """Fetch many rows by id, preserving no particular order."""
    if not item_ids:
        return {}
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(_SELECT + f"WHERE id IN ({placeholders})", item_ids).fetchall()
    return {row["id"]: _row_to_item(row) for row in rows}


def count_rows(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT count(*) FROM raw_items").fetchone()[0])


def parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse the datetime strings SQLite hands back, tolerating variation."""
    if not value:
        return None
    text = value.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
