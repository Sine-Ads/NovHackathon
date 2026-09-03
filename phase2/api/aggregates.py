"""Whitelisted aggregate queries over the read-only corpus.

The model never writes SQL. It names one of these functions and supplies
arguments; the backend runs the query and hands back the result as FACTS. The
set is small because the shape of counting questions a stakeholder asks is
predictable, and text-to-SQL against a live database is a failure mode nobody
needs during a demo.
"""
from __future__ import annotations

import collections
import sqlite3
from typing import Any, Optional

from api import source_db
from api.landscape import normalize_condition, normalize_sponsor

DIMENSIONS = ("source", "status", "sponsor", "condition", "year")


def _matches(
    item: source_db.SourceItem,
    source: Optional[str],
    status: Optional[str],
    sponsor_contains: Optional[str],
) -> bool:
    if source and source.lower() not in item.source_name.lower():
        return False
    if status:
        actual = (item.metadata.get("overall_status") or "").upper()
        if actual != status.upper():
            return False
    if sponsor_contains:
        sponsor = (item.metadata.get("lead_sponsor") or "") + " " + (
            item.metadata.get("company_name") or ""
        )
        if sponsor_contains.lower() not in sponsor.lower():
            return False
    return True


def count_items(
    conn: sqlite3.Connection,
    source: Optional[str] = None,
    status: Optional[str] = None,
    sponsor_contains: Optional[str] = None,
) -> dict[str, Any]:
    total = sum(
        1
        for item in source_db.iter_items(conn)
        if _matches(item, source, status, sponsor_contains)
    )
    return {
        "query": "count_items",
        "filters": {
            "source": source,
            "status": status,
            "sponsor_contains": sponsor_contains,
        },
        "count": total,
    }


def group_count(
    conn: sqlite3.Connection,
    dimension: str = "source",
    limit: int = 15,
    source: Optional[str] = None,
    status: Optional[str] = None,
    sponsor_contains: Optional[str] = None,
) -> dict[str, Any]:
    if dimension not in DIMENSIONS:
        return {"error": f"unknown dimension {dimension!r}; allowed: {list(DIMENSIONS)}"}

    counter: collections.Counter = collections.Counter()
    for item in source_db.iter_items(conn):
        if not _matches(item, source, status, sponsor_contains):
            continue
        meta = item.metadata
        if dimension == "source":
            counter[item.source_name] += 1
        elif dimension == "status":
            if meta.get("overall_status"):
                counter[meta["overall_status"]] += 1
        elif dimension == "sponsor":
            name = meta.get("lead_sponsor") or meta.get("company_name")
            if name:
                counter[normalize_sponsor(name)] += 1
        elif dimension == "condition":
            for cond in meta.get("conditions") or []:
                counter[normalize_condition(cond)] += 1
        elif dimension == "year":
            if item.date_published:
                counter[item.date_published[:4]] += 1

    return {
        "query": "group_count",
        "dimension": dimension,
        "results": counter.most_common(max(1, min(limit, 50))),
    }


def list_items(
    conn: sqlite3.Connection,
    source: Optional[str] = None,
    status: Optional[str] = None,
    sponsor_contains: Optional[str] = None,
    limit: int = 20,
) -> dict[str, Any]:
    rows = []
    for item in source_db.iter_items(conn):
        if not _matches(item, source, status, sponsor_contains):
            continue
        rows.append(
            {
                "item_id": item.item_id,
                "source": item.source_name,
                "source_id": item.source_id,
                "title": item.title,
                "date": item.date_published,
                "status": item.metadata.get("overall_status"),
                "sponsor": item.metadata.get("lead_sponsor"),
            }
        )
        if len(rows) >= max(1, min(limit, 50)):
            break
    return {"query": "list_items", "count": len(rows), "items": rows}


REGISTRY = {
    "count_items": count_items,
    "group_count": group_count,
    "list_items": list_items,
}


def run(conn: sqlite3.Connection, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a whitelisted aggregate, ignoring any argument it does not accept."""
    func = REGISTRY.get(name)
    if func is None:
        return {"error": f"unknown query {name!r}; allowed: {list(REGISTRY)}"}
    allowed = func.__code__.co_varnames[: func.__code__.co_argcount]
    safe = {k: v for k, v in (args or {}).items() if k in allowed and k != "conn"}
    try:
        return func(conn, **safe)
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}


def to_facts_block(result: dict[str, Any]) -> str:
    """Render a result as compact text for the prompt."""
    if "error" in result:
        return f"Query failed: {result['error']}"
    if result.get("query") == "count_items":
        filters = {k: v for k, v in result["filters"].items() if v}
        scope = f" ({filters})" if filters else " (whole corpus)"
        return f"count{scope} = {result['count']}"
    if result.get("query") == "group_count":
        lines = [f"counts by {result['dimension']}:"]
        lines += [f"  {label}: {count}" for label, count in result["results"]]
        return "\n".join(lines)
    if result.get("query") == "list_items":
        lines = [f"{result['count']} matching records:"]
        for row in result["items"]:
            lines.append(
                f"  [id:{row['item_id']}] {row['source']} {row['source_id']} — "
                f"{(row['title'] or '')[:80]}"
                + (f" (status {row['status']})" if row["status"] else "")
            )
        return "\n".join(lines)
    return str(result)
