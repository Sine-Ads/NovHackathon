"""FastAPI application for the Phase 2 intelligence UI."""
from __future__ import annotations

import json
import sqlite3
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api import (
    chat,
    classifications,
    config,
    embed,
    landscape,
    retrieval,
    signals as signals_mod,
    source_db,
    store,
    summarize,
)

STATE: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Both connections are opened with check_same_thread=False because FastAPI
    # runs sync endpoints on a worker threadpool. Writes go only to the sidecar
    # database; the source connection is read-only at the SQLite level.
    STATE["src"] = sqlite3.connect(config.read_only_uri(), uri=True, check_same_thread=False)
    STATE["src"].row_factory = sqlite3.Row
    source_db.assert_schema(STATE["src"])

    STATE["side"] = sqlite3.connect(config.sidecar_db_path(), check_same_thread=False)
    STATE["side"].row_factory = sqlite3.Row
    STATE["side"].execute("PRAGMA journal_mode=WAL")
    STATE["side"].executescript(store.SCHEMA)

    # The entire embedding table is 2.1 MB, so it lives in memory for the
    # lifetime of the process and every query is one matrix multiply.
    STATE["index"] = embed.VectorIndex.load(STATE["side"])
    yield
    for key in ("src", "side"):
        if STATE.get(key):
            STATE[key].close()


app = FastAPI(title="Haemophilia Intelligence Radar — Phase 2", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def src() -> sqlite3.Connection:
    return STATE["src"]


def side() -> sqlite3.Connection:
    return STATE["side"]


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    stats = store.index_stats(side())
    verdicts = classifications.counts(src())
    gaps = [
        "ClinicalTrials.gov records carry no intervention/drug names, so drug "
        "questions rely on full-text search rather than structured filters.",
        "SEC EDGAR records are filing index stubs, not full filing text.",
    ]
    if not verdicts["available"]:
        gaps.append(
            "The classifications table does not exist yet — run "
            "'alembic upgrade head' in data-ingestion-system, then the classifier. "
            "Verdict badges and filters stay hidden until then."
        )
    elif verdicts["unclassified"]:
        gaps.append(
            f"{verdicts['unclassified']} of {verdicts.get('corpus', 0)} records have "
            "no classification yet."
        )
    return {
        "status": "ok",
        "source_db": str(config.source_db_path()),
        "source_rows": source_db.count_rows(src()),
        "sidecar_db": str(config.sidecar_db_path()),
        "index": stats,
        "vectors_loaded": len(STATE["index"]),
        "llm_model": config.LLM_MODEL,
        "embed_model": config.EMBED_MODEL,
        "llm_configured": bool(config.HF_TOKEN),
        "index_complete": stats["embeddings"] >= stats["chunks"] > 0,
        "classifications": verdicts,
        "known_gaps": gaps,
    }


@app.post("/api/classifications/recheck")
def recheck_classifications() -> dict:
    """Re-detect the classifications table without restarting the API.

    Lets a teammate run 'alembic upgrade head' and the classifier while this
    process stays up.
    """
    available = classifications.available(src(), recheck=True)
    return {"available": available, "counts": classifications.counts(src())}


@app.get("/api/landscape")
def get_landscape() -> dict:
    stats = store.get_landscape(side())
    if not stats:
        raise HTTPException(503, "Landscape not computed. Run scripts/build_index.py")
    return stats


@app.post("/api/landscape/refresh")
def refresh_landscape() -> dict:
    stats = landscape.compute(src())
    store.put_landscape(side(), stats)
    return stats


@app.get("/api/facets")
def facets() -> dict:
    sources = [
        {"name": r["source_name"], "count": r["n"]}
        for r in side().execute(
            "SELECT source_name, count(*) n FROM item GROUP BY 1 ORDER BY n DESC"
        )
    ]
    statuses = [
        {"name": r["status"], "count": r["n"]}
        for r in side().execute(
            """SELECT json_extract(metadata_json,'$.overall_status') status, count(*) n
               FROM item WHERE status IS NOT NULL GROUP BY 1 ORDER BY n DESC"""
        )
    ]
    verdicts = classifications.counts(src())
    # Only real verdicts are offered as filters. 'failed' is exposed separately
    # so operators can review it without it reading as a fifth category.
    categories = [
        {
            "name": name,
            "label": classifications.CATEGORY_LABELS[name],
            "count": count,
        }
        for name, count in verdicts["by_category"].items()
    ]
    derived = signals_mod.facet_counts(side(), src())
    return {
        "sources": sources,
        "trial_statuses": statuses,
        "categories": categories,
        "classifications_available": verdicts["available"],
        "failed_count": verdicts["failed"],
        # Derived dimensions, so the filter rail offers only what the corpus has.
        "kinds": derived["kinds"],
        "urgencies": derived["urgencies"],
        "indications": derived["indications"],
        "reviewed_count": derived["reviewed_count"],
        "unreviewed_count": derived["unreviewed_count"],
        "with_change_count": derived["with_change_count"],
    }


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------


def _card(row: sqlite3.Row) -> dict:
    from api.evidence import DATE_LABELS

    metadata = json.loads(row["metadata_json"] or "{}")
    snippet = (row["snippet"] or "").strip().replace("\n", " ")
    return {
        "item_id": row["item_id"],
        "source_name": row["source_name"],
        "source_id": row["source_id"],
        "source_url": row["source_url"],
        "title": row["title"],
        "date_published": row["date_published"],
        "date_ingested": row["date_ingested"],
        "date_class": row["date_class"],
        "date_label": DATE_LABELS.get(row["date_class"], "Date unknown"),
        "is_thin": bool(row["is_thin"]),
        "n_chars": row["n_chars"],
        "snippet": snippet[:280],
        "status": metadata.get("overall_status"),
        "sponsor": metadata.get("lead_sponsor") or metadata.get("company_name"),
        "journal": metadata.get("journal"),
        "openfda_type": metadata.get("type"),
    }


@app.get("/api/feed")
def feed(
    q: Optional[str] = None,
    source: Optional[list[str]] = Query(None),
    status: Optional[list[str]] = Query(None),
    category: Optional[list[str]] = Query(None),
    sort: str = "date",
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """Browse or search. A query switches ordering to relevance."""
    # Classification filters resolve to a set of ids up front, because the
    # verdicts live in the source database while the feed reads the sidecar.
    allowed_ids: Optional[set[str]] = None
    if category:
        allowed_ids = set()
        for name in category:
            allowed_ids |= classifications.ids_in_category(src(), name)

    if q:
        hits = retrieval.hybrid_search(
            side(), STATE["index"], q, k=200, sources=source, statuses=status
        )
        if allowed_ids is not None:
            hits = [h for h in hits if h.item_id in allowed_ids]
        window = hits[offset : offset + limit]
        if not window:
            return {"items": [], "total": len(hits), "mode": "relevance"}
        ids = [h.item_id for h in window]
        placeholders = ",".join("?" * len(ids))
        rows = {
            r["item_id"]: r
            for r in side().execute(
                f"""SELECT i.*, substr(c.text, 1, 400) snippet
                    FROM item i LEFT JOIN chunk c
                      ON c.item_id = i.item_id AND c.chunk_index = 0
                    WHERE i.item_id IN ({placeholders})""",
                ids,
            )
        }
        verdicts = classifications.for_items(src(), ids)
        items = []
        for hit in window:
            row = rows.get(hit.item_id)
            if row is None:
                continue
            card = _card(row)
            card["match_reason"] = hit.reason
            card["score"] = round(hit.evidence_score, 6)
            card["classification"] = verdicts.get(hit.item_id)
            items.append(card)
        return {"items": items, "total": len(hits), "mode": "relevance"}

    where, params = ["1=1"], []
    if source:
        where.append(f"i.source_name IN ({','.join('?' * len(source))})")
        params += source
    if status:
        where.append(
            f"json_extract(i.metadata_json,'$.overall_status') IN "
            f"({','.join('?' * len(status))})"
        )
        params += [s.upper() for s in status]
    if allowed_ids is not None:
        if not allowed_ids:
            return {"items": [], "total": 0, "mode": "browse"}
        where.append(f"i.item_id IN ({','.join('?' * len(allowed_ids))})")
        params += sorted(allowed_ids)

    # NULLS LAST is not portable across SQLite builds; the boolean sort key is.
    # 268 of 299 PubMed rows are undated, so this ordering is load-bearing.
    order = {
        "date": "i.date_published IS NULL, i.date_published DESC",
        "date_asc": "i.date_published IS NULL, i.date_published ASC",
        "title": "i.title COLLATE NOCASE ASC",
        "source": "i.source_name ASC, i.date_published DESC",
    }.get(sort, "i.date_published IS NULL, i.date_published DESC")

    clause = " AND ".join(where)
    total = side().execute(
        f"SELECT count(*) FROM item i WHERE {clause}", params
    ).fetchone()[0]
    rows = side().execute(
        f"""SELECT i.*, substr(c.text, 1, 400) snippet
            FROM item i LEFT JOIN chunk c
              ON c.item_id = i.item_id AND c.chunk_index = 0
            WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    verdicts = classifications.for_items(src(), [r["item_id"] for r in rows])
    cards = []
    for row in rows:
        card = _card(row)
        card["classification"] = verdicts.get(row["item_id"])
        cards.append(card)
    return {"items": cards, "total": total, "mode": "browse"}


@app.get("/api/items/{item_id}")
def get_item(item_id: str) -> dict:
    item = source_db.get_item(src(), item_id)
    if item is None:
        raise HTTPException(404, f"Unknown item {item_id}")
    from api.evidence import DATE_LABELS

    return {
        "item_id": item.item_id,
        "source_name": item.source_name,
        "source_id": item.source_id,
        "source_url": item.source_url,
        "title": item.title,
        "raw_content": item.raw_content,
        "date_published": item.date_published,
        "date_ingested": item.date_ingested,
        "date_class": item.date_class,
        "date_label": DATE_LABELS.get(item.date_class, "Date unknown"),
        "metadata": item.metadata,
        "is_thin": summarize.is_thin(item),
        "classification": classifications.for_item(src(), item_id),
    }


@app.post("/api/items/{item_id}/summary")
def item_summary(item_id: str, force: bool = False) -> dict:
    item = source_db.get_item(src(), item_id)
    if item is None:
        raise HTTPException(404, f"Unknown item {item_id}")
    payload = summarize.summarize(side(), item, force=force)
    payload["item_id"] = item_id
    payload["provenance"] = {
        "source_name": item.source_name,
        "source_id": item.source_id,
        "source_url": item.source_url,
        "date_published": item.date_published,
        "date_class": item.date_class,
    }
    return payload


@app.get("/api/items/{item_id}/similar")
def item_similar(item_id: str, k: int = Query(6, ge=1, le=20)) -> dict:
    hits = retrieval.similar_items(side(), STATE["index"], item_id, k=k)
    verdicts = classifications.for_items(src(), [h.item_id for h in hits])
    for hit in hits:
        hit.classification = verdicts.get(hit.item_id)
    return {"item_id": item_id, "similar": [h.to_dict() for h in hits]}


# ---------------------------------------------------------------------------
# Signals
#
# The same corpus as /api/feed, seen as events rather than documents. Urgency
# and indication are derived per row rather than stored, so those two filters
# and the urgency sort are applied in Python after the SQL filters have cut the
# set down. At corpus scale (1,399 records) that is a single cheap pass.
# ---------------------------------------------------------------------------

SIGNAL_COLUMNS = """SELECT i.*, substr(c.text, 1, 400) snippet
                    FROM item i LEFT JOIN chunk c
                      ON c.item_id = i.item_id AND c.chunk_index = 0"""

URGENCY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _desc(value: Optional[str]) -> tuple:
    """Sort key that puts later dates first without reversing the whole tuple."""
    return tuple(-ord(c) for c in (value or ""))


def _signal_rows(
    q: Optional[str],
    source: Optional[list[str]],
    status: Optional[list[str]],
    allowed_ids: Optional[set[str]],
) -> tuple[list[sqlite3.Row], dict[str, str], str]:
    """Rows matching the SQL-expressible filters, plus per-row match reasons."""
    if q:
        hits = retrieval.hybrid_search(
            side(), STATE["index"], q, k=200, sources=source, statuses=status
        )
        if allowed_ids is not None:
            hits = [h for h in hits if h.item_id in allowed_ids]
        if not hits:
            return [], {}, "relevance"
        ids = [h.item_id for h in hits]
        placeholders = ",".join("?" * len(ids))
        by_id = {
            r["item_id"]: r
            for r in side().execute(
                f"{SIGNAL_COLUMNS} WHERE i.item_id IN ({placeholders})", ids
            )
        }
        rows = [by_id[h.item_id] for h in hits if h.item_id in by_id]
        return rows, {h.item_id: h.reason for h in hits}, "relevance"

    where, params = ["1=1"], []
    if source:
        where.append(f"i.source_name IN ({','.join('?' * len(source))})")
        params += source
    if status:
        where.append(
            f"json_extract(i.metadata_json,'$.overall_status') IN "
            f"({','.join('?' * len(status))})"
        )
        params += [s.upper() for s in status]
    if allowed_ids is not None:
        if not allowed_ids:
            return [], {}, "browse"
        where.append(f"i.item_id IN ({','.join('?' * len(allowed_ids))})")
        params += sorted(allowed_ids)
    clause = " AND ".join(where)
    rows = side().execute(f"{SIGNAL_COLUMNS} WHERE {clause}", params).fetchall()
    return rows, {}, "browse"


@app.get("/api/signals")
def signals_feed(
    q: Optional[str] = None,
    source: Optional[list[str]] = Query(None),
    status: Optional[list[str]] = Query(None),
    category: Optional[list[str]] = Query(None, description="Phase 1 classifier verdict"),
    kind: Optional[list[str]] = Query(None, description="Derived category: Trial, Publication…"),
    urgency: Optional[list[str]] = Query(None),
    indication: Optional[list[str]] = Query(None),
    reviewed: Optional[str] = Query(None, pattern="^(all|reviewed|unreviewed)$"),
    changed_only: bool = False,
    sort: str = "urgency",
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    allowed_ids: Optional[set[str]] = None
    if category:
        allowed_ids = set()
        for name in category:
            allowed_ids |= classifications.ids_in_category(src(), name)

    rows, reasons, mode = _signal_rows(q, source, status, allowed_ids)
    built = signals_mod.build(side(), src(), rows)
    for signal in built:
        if signal["id"] in reasons:
            signal["match_reason"] = reasons[signal["id"]]

    if kind:
        wanted = set(kind)
        built = [s for s in built if s["category"] in wanted]
    if urgency:
        wanted = {u.upper() for u in urgency}
        built = [s for s in built if s["urgency"] in wanted]
    if indication:
        # "unstated" is a selectable value: a record that names no indication is
        # a real thing to filter for, not a gap to hide.
        wanted = set(indication)
        built = [
            s
            for s in built
            if (s["indication"] or "Indication unstated") in wanted
        ]
    if reviewed == "reviewed":
        built = [s for s in built if s["reviewed"]]
    elif reviewed == "unreviewed":
        built = [s for s in built if not s["reviewed"]]
    if changed_only:
        built = [s for s in built if s["what_changed"] is not None]

    # Relevance order is the retrieval ranking and is never re-sorted; asking
    # for the best match and getting it reordered by urgency would be a lie.
    if mode != "relevance":
        if sort == "urgency":
            built.sort(
                key=lambda s: (URGENCY_ORDER[s["urgency"]], -s["score"], s["detected_date"] or ""),
            )
        elif sort == "detected":
            built.sort(key=lambda s: s["detected_date"] or "", reverse=True)
        elif sort == "date":
            # Undated rows go last rather than first: 268 of 299 PubMed records
            # have no publication date, and an empty string sorts before every
            # real one.
            built.sort(
                key=lambda s: (s["date_published"] is None, _desc(s["date_published"]))
            )
        elif sort == "title":
            built.sort(key=lambda s: (s["title"] or "").lower())
        elif sort == "source":
            built.sort(key=lambda s: (s["source_name"], s["date_published"] or ""))

    total = len(built)
    return {"items": built[offset : offset + limit], "total": total, "mode": mode}


@app.get("/api/signals/{item_id}")
def signal_detail(item_id: str) -> dict:
    row = side().execute(
        f"{SIGNAL_COLUMNS} WHERE i.item_id = ?", (item_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Unknown item {item_id}")
    built = signals_mod.build(side(), src(), [row])[0]
    built["changes"] = store.changes_for_item(side(), item_id)
    built["evidence"] = signals_mod.evidence_for(
        side(), src(), STATE["index"], item_id, k=6
    )
    return built


@app.post("/api/signals/{item_id}/review")
def signal_review(item_id: str, body: dict = Body(default=None)) -> dict:
    exists = side().execute(
        "SELECT 1 FROM item WHERE item_id = ?", (item_id,)
    ).fetchone()
    if exists is None:
        raise HTTPException(404, f"Unknown item {item_id}")
    current = store.reviewed_map(side(), [item_id]).get(item_id, False)
    wanted = (body or {}).get("reviewed")
    reviewed = (not current) if wanted is None else bool(wanted)
    store.set_reviewed(side(), item_id, reviewed)
    signals_mod.invalidate_facets()
    return {"item_id": item_id, "reviewed": reviewed}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@app.post("/api/chat/item/{item_id}")
def chat_item(item_id: str, body: dict = Body(...)) -> StreamingResponse:
    message = (body or {}).get("message", "").strip()
    if not message:
        raise HTTPException(400, "message is required")
    return StreamingResponse(
        chat.item_chat(src(), side(), STATE["index"], item_id, message),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post("/api/chat/global")
def chat_global(body: dict = Body(...)) -> StreamingResponse:
    message = (body or {}).get("message", "").strip()
    if not message:
        raise HTTPException(400, "message is required")
    thread_id = (body or {}).get("thread_id") or "global"
    return StreamingResponse(
        chat.global_chat(src(), side(), STATE["index"], message, thread_id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.get("/api/threads/{thread_id}")
def thread_history(thread_id: str) -> dict:
    return {"thread_id": thread_id, "messages": store.get_history(side(), thread_id)}


# ---------------------------------------------------------------------------
# Classification API — the contract from FRONTEND_INTEGRATION.md
#
# That document specifies GET /papers, GET /papers/{raw_item_id} and
# GET /categories/{category}, with a flat JSON shape keyed on `id`, `source`,
# `abstract` and `published_at`. The radar's own endpoints use different names
# (`item_id`, `source_name`, `raw_content`, `date_published`) and carry more
# detail, so rather than renaming those and breaking the UI, these routes serve
# the documented shape alongside them. Anything written against the document
# works unchanged; the radar keeps its richer payloads.
# ---------------------------------------------------------------------------


def _paper(item: source_db.SourceItem, verdict: Optional[dict]) -> dict:
    """The exact shape FRONTEND_INTEGRATION.md specifies."""
    verdict = verdict or {}
    return {
        "id": item.item_id,
        "title": item.title,
        "source": item.source_name,
        "source_id": item.source_id,
        "source_url": item.source_url,
        "abstract": item.raw_content,
        "published_at": item.date_published,
        "category": verdict.get("category"),
        "justification": verdict.get("justification"),
        "method": verdict.get("method"),
        "status": verdict.get("status"),
        "reason": verdict.get("reason"),
        "classified_at": verdict.get("classified_at"),
        "metadata": item.metadata,
    }


@app.get("/api/papers")
def papers(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="classified | failed"),
) -> dict:
    """Paginated papers with their classification, newest verdict first.

    Records the classifier has not reached are included with null classification
    fields, so the endpoint reports the corpus rather than only the part that
    has been processed.
    """
    if not classifications.available(src()):
        raise HTTPException(
            503,
            "The classifications table does not exist yet. Run 'alembic upgrade head' "
            "in data-ingestion-system and then the classifier.",
        )
    where = ""
    params: list = []
    if status == "failed":
        where = "WHERE c.status = 'failed' OR c.category IS NULL"
    elif status == "classified":
        where = "WHERE c.status != 'failed' AND c.category IS NOT NULL"

    total = src().execute(
        f"SELECT count(*) FROM classifications c {where}", params
    ).fetchone()[0]
    rows = src().execute(
        f"""SELECT c.raw_item_id FROM classifications c {where}
            ORDER BY c.classified_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()

    ids = [r["raw_item_id"] for r in rows]
    items = source_db.get_items(src(), ids)
    verdicts = classifications.for_items(src(), ids)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "papers": [
            _paper(items[i], verdicts.get(i)) for i in ids if i in items
        ],
    }


@app.get("/api/papers/{raw_item_id}")
def paper(raw_item_id: str) -> dict:
    item = source_db.get_item(src(), raw_item_id)
    if item is None:
        raise HTTPException(404, f"Unknown record {raw_item_id}")
    return _paper(item, classifications.for_item(src(), raw_item_id))


@app.get("/api/categories/{category}")
def by_category(
    category: str,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """Papers carrying one verdict.

    'failed' is accepted so operators can review what the classifier could not
    handle — the document asks for those to stay visible without being
    presented as a category.
    """
    if category not in classifications.CATEGORIES and category != "failed":
        raise HTTPException(
            404,
            f"Unknown category {category!r}. Valid: "
            f"{list(classifications.CATEGORIES) + ['failed']}",
        )
    if not classifications.available(src()):
        raise HTTPException(503, "The classifications table does not exist yet.")

    ids = sorted(classifications.ids_in_category(src(), category))
    window = ids[offset : offset + limit]
    items = source_db.get_items(src(), window)
    verdicts = classifications.for_items(src(), window)
    return {
        "category": category,
        "label": classifications.CATEGORY_LABELS.get(category, "Failed"),
        "total": len(ids),
        "papers": [_paper(items[i], verdicts.get(i)) for i in window if i in items],
    }
