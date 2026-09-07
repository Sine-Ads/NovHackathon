"""The signal view: what Phase 2 can honestly say about a record as an event.

A "signal" here is not a new object in the corpus. It is a record from Phase 1
seen through three derivations, each computed from data that actually exists:

* **category** — from the source that supplied the record.
* **indication** — from haemophilia A / B wording in the title and metadata.
* **urgency** — a product of factors already used for evidence ranking, plus
  what changed and what Phase 1's classifier concluded.

Fields the radar mock-up carried that this corpus cannot support — geography,
modality, therapeutic modality, routing decisions — are absent rather than
guessed. An empty field is a fact about the corpus; an invented one is not.

Nothing here calls a model. Every value is reproducible from the database.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Optional

from api import classifications, evidence as evidence_mod, retrieval, store
from api.evidence import DATE_LABELS, Evidence

# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

#: Phase 1 ingests four sources, and each speaks to exactly one kind of event.
#: The radar mock-up also offered Regulatory, HTA, Congress, Safety and Silence
#: — none of which has a source behind it here, so none is ever emitted. The
#: facets endpoint reports only the categories actually present.
CATEGORY_BY_SOURCE: dict[str, str] = {
    "ClinicalTrials.gov": "Trial",
    "PubMed (NCBI)": "Publication",
    "arXiv": "Publication",
    "SEC EDGAR": "Corporate",
}

OTHER_CATEGORY = "Other"


def category_for(source_name: str) -> str:
    return CATEGORY_BY_SOURCE.get(source_name, OTHER_CATEGORY)


# ---------------------------------------------------------------------------
# Indication
# ---------------------------------------------------------------------------

# Both spellings appear across the corpus; PubMed favours "hemophilia", the
# trial registry and European sources "haemophilia".
_HAEM = r"ha?emophilia"

#: "Haemophilia A and B" names both and must not resolve to A alone.
_BOTH = re.compile(rf"{_HAEM}[\s\-]+a\s*(?:and|&|/|\+|or)\s*b\b", re.I)

_A_PATTERNS = (
    re.compile(rf"{_HAEM}[\s\-]+a\b", re.I),
    re.compile(r"factor\s+viii", re.I),
    re.compile(r"\bantiha?emophilic\s+factor\b", re.I),
)
_B_PATTERNS = (
    re.compile(rf"{_HAEM}[\s\-]+b\b", re.I),
    re.compile(r"factor\s+ix", re.I),
    re.compile(r"\bchristmas\s+disease\b", re.I),
)
# Case-sensitive on purpose: lowercase "fix" is an ordinary English word, and
# matching it would tag half the corpus as haemophilia B.
_A_ABBREV = re.compile(r"\bFVIII\b")
_B_ABBREV = re.compile(r"\bFIX\b")

INDICATION_A = "Haemophilia A"
INDICATION_B = "Haemophilia B"
INDICATION_BOTH = "Haemophilia A and B"


def indication_for(title: Optional[str], metadata: dict[str, Any]) -> Optional[str]:
    """Which haemophilia the record names, or None when it does not say.

    None is a real answer: a paper on general coagulation, or a 10-Q covering a
    whole portfolio, names neither. The UI says "indication unstated" rather
    than picking one.
    """
    parts = [title or "", str(metadata.get("official_title") or "")]
    for key in ("conditions", "mesh_terms", "categories"):
        value = metadata.get(key)
        if isinstance(value, (list, tuple)):
            parts.extend(str(v) for v in value)
        elif value:
            parts.append(str(value))
    haystack = " ".join(parts)

    both = bool(_BOTH.search(haystack))
    is_a = both or any(p.search(haystack) for p in _A_PATTERNS) or bool(_A_ABBREV.search(haystack))
    is_b = both or any(p.search(haystack) for p in _B_PATTERNS) or bool(_B_ABBREV.search(haystack))
    if is_a and is_b:
        return INDICATION_BOTH
    if is_a:
        return INDICATION_A
    if is_b:
        return INDICATION_B
    return None


# ---------------------------------------------------------------------------
# Urgency
# ---------------------------------------------------------------------------

#: A field that moved says more than a record merely appearing, and a trial
#: changing status says more than either. These are the only three states the
#: change log can produce, so the ladder has three rungs and no more.
CHANGE_WEIGHTS: dict[str, float] = {
    "overall_status": 1.50,
    "_field": 1.25,
    "record": 1.00,
}

#: A settled verdict is more decision-relevant than an open one. The spread is
#: deliberately narrow — this is a nudge, not a ranking of its own, and a record
#: with no verdict is never penalised for it.
VERDICT_WEIGHTS: dict[str, float] = {
    "proven_right": 1.10,
    "proven_false": 1.10,
    "proven_false_but_useful": 1.05,
    "still_working_on": 1.00,
}

# Calibrated against the corpus rather than guessed. With completeness capped at
# 1.00 and recency at 1.10, a record that has never been observed to change tops
# out at 1.07, so any threshold above that would make HIGH unreachable until a
# second ingestion run — an empty tier is not a useful one. At 1.02 the HIGH
# band is the 28 complete records with a real publication or filing date inside
# the last ~2 years, and a trial that changes status (x1.50) clears it outright.
HIGH_THRESHOLD = 1.02
MEDIUM_THRESHOLD = 0.95


def _direction(weight: float) -> str:
    if weight > 1.0:
        return "up"
    if weight < 1.0:
        return "down"
    return "neutral"


def urgency_for(
    n_chars: int,
    is_thin: bool,
    date_published: Optional[str],
    date_class: str,
    change: Optional[dict[str, Any]],
    verdict: Optional[dict[str, Any]],
) -> tuple[str, float, list[dict[str, Any]]]:
    """Bucket, score and the factors that produced them.

    The completeness and recency factors are the same functions evidence
    ranking uses (``api/evidence.py``), so a record cannot be urgent here and
    unremarkable there. The returned breakdown *is* the calculation — the UI
    renders it verbatim, which is why nothing in it can be a label without a
    number behind it.
    """
    completeness = evidence_mod.completeness_factor(n_chars, is_thin)
    recency = evidence_mod.recency_factor(date_published, date_class)

    if change is None:
        weight, change_label = 1.0, "No change recorded"
    elif change["field"] == "record":
        weight, change_label = CHANGE_WEIGHTS["record"], "First seen in corpus"
    else:
        weight = change_weight(change["field"])
        change_label = f"{change['field_label']} changed"

    category = (verdict or {}).get("category")
    verdict_weight = VERDICT_WEIGHTS.get(category, 1.0) if category else 1.0
    verdict_label = (
        f"Verdict: {verdict['category_label']}" if category else "No classifier verdict"
    )

    score = completeness * recency * weight * verdict_weight
    if score >= HIGH_THRESHOLD:
        bucket = "HIGH"
    elif score >= MEDIUM_THRESHOLD:
        bucket = "MEDIUM"
    else:
        bucket = "LOW"

    breakdown = [
        {"feature": change_label, "weight": weight, "direction": _direction(weight)},
        {
            "feature": "Record completeness" + (" (stub)" if is_thin else ""),
            "weight": completeness,
            "direction": _direction(completeness),
        },
        {
            "feature": "Recency"
            + ("" if date_class in ("publication", "filing") else " (not a dated event)"),
            "weight": recency,
            "direction": _direction(recency),
        },
        {"feature": verdict_label, "weight": verdict_weight, "direction": _direction(verdict_weight)},
    ]
    return bucket, score, breakdown


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def change_weight(field: str) -> float:
    if field in CHANGE_WEIGHTS:
        return CHANGE_WEIGHTS[field]
    return CHANGE_WEIGHTS["_field"]


def _headline_change(changes: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The change a row leads with.

    Newest first, and within one observation the heaviest field wins: a trial
    that changed status and sponsor in the same build leads with the status.
    """
    if not changes:
        return None
    return max(changes, key=lambda c: (c["detected_at"], change_weight(c["field"])))


def to_signal(
    row: sqlite3.Row,
    changes: list[dict[str, Any]],
    verdict: Optional[dict[str, Any]],
    reviewed: bool,
) -> dict[str, Any]:
    """One feed row, from a sidecar ``item`` row plus its history and verdict."""
    metadata = json.loads(row["metadata_json"] or "{}")
    snippet = (row["snippet"] or "").strip().replace("\n", " ") if "snippet" in row.keys() else ""
    change = _headline_change(changes)
    is_thin = bool(row["is_thin"])

    urgency, score, breakdown = urgency_for(
        n_chars=row["n_chars"],
        is_thin=is_thin,
        date_published=row["date_published"],
        date_class=row["date_class"],
        change=change,
        verdict=verdict,
    )

    return {
        "id": row["item_id"],
        # Emitted twice on purpose: "id" is what the signal views key on, and
        # "item_id" is what every existing record component already reads, so
        # the summary panel and chat work against a signal unmodified.
        "item_id": row["item_id"],
        "title": row["title"],
        "category": category_for(row["source_name"]),
        "indication": indication_for(row["title"], metadata),
        "urgency": urgency,
        "score": round(score, 4),
        "score_breakdown": breakdown,
        # None when nothing has been observed to move. The row hides its diff
        # line rather than showing an empty before/after.
        "what_changed": None if change is None or change["field"] == "record" else change,
        "detected_date": change["detected_at"] if change else row["date_ingested"],
        "detected_label": "First seen" if change is None or change["field"] == "record"
        else f"{change['field_label']} changed",
        "change_count": len(changes),
        "reviewed": reviewed,
        "classification": verdict,
        # Provenance, carried through unchanged from the record feed so a signal
        # can always be traced back to its source.
        "source_name": row["source_name"],
        "source_id": row["source_id"],
        "source_url": row["source_url"],
        "date_published": row["date_published"],
        "date_class": row["date_class"],
        "date_label": DATE_LABELS.get(row["date_class"], "Date unknown"),
        "is_thin": is_thin,
        "n_chars": row["n_chars"],
        "snippet": snippet[:280],
        "status": metadata.get("overall_status"),
        "sponsor": metadata.get("lead_sponsor") or metadata.get("company_name"),
        "journal": metadata.get("journal"),
    }


def build(
    side: sqlite3.Connection,
    src: sqlite3.Connection,
    rows: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    """Signals for a page of item rows, with one query per lookup table."""
    item_ids = [row["item_id"] for row in rows]
    changes = store.changes_for_items(side, item_ids)
    verdicts = classifications.for_items(src, item_ids)
    reviewed = store.reviewed_map(side, item_ids)
    return [
        to_signal(
            row,
            changes.get(row["item_id"], []),
            verdicts.get(row["item_id"]),
            reviewed.get(row["item_id"], False),
        )
        for row in rows
    ]


def evidence_for(
    side: sqlite3.Connection,
    src: sqlite3.Connection,
    index: Any,
    item_id: str,
    k: int = 6,
) -> list[dict[str, Any]]:
    """The record's own text first, then its nearest neighbours.

    The record itself leads because it is what the signal is *about*; the
    neighbours are corroboration. Both carry the full scoring trail, so the
    drawer can say why each one is there.
    """
    row = side.execute(
        """SELECT i.*, c.chunk_id, c.text
           FROM item i LEFT JOIN chunk c
             ON c.item_id = i.item_id AND c.chunk_index = 0
           WHERE i.item_id = ?""",
        (item_id,),
    ).fetchone()
    if row is None:
        return []

    own = Evidence(
        chunk_id=row["chunk_id"] or f"{item_id}#0",
        item_id=item_id,
        source_name=row["source_name"],
        source_id=row["source_id"],
        source_url=row["source_url"],
        title=row["title"],
        date_published=row["date_published"],
        date_class=row["date_class"],
        matched_by=["record"],
        n_chars=row["n_chars"],
        is_thin=bool(row["is_thin"]),
        text=row["text"] or "",
        reason="the record this signal is derived from",
        completeness=evidence_mod.completeness_factor(row["n_chars"], bool(row["is_thin"])),
        recency=evidence_mod.recency_factor(row["date_published"], row["date_class"]),
    )
    own.classification = classifications.for_item(src, item_id)

    neighbours = retrieval.similar_items(side, index, item_id, k=k)
    verdicts = classifications.for_items(src, [n.item_id for n in neighbours])
    for neighbour in neighbours:
        neighbour.classification = verdicts.get(neighbour.item_id)

    return [own.to_dict(include_text=True)] + [n.to_dict(include_text=True) for n in neighbours]


# ---------------------------------------------------------------------------
# Facet counts
#
# Urgency and indication are computed, not stored, so their counts need a pass
# over the corpus. At 1,399 records that is tens of milliseconds; the cache
# below keeps a page load from paying it twice. If the corpus grows past a few
# tens of thousands, these become columns on ``item`` written at index time.
# ---------------------------------------------------------------------------

_FACET_CACHE: dict[str, Any] = {"key": None, "value": None}


def _corpus_key(side: sqlite3.Connection) -> tuple[int, int, int]:
    return tuple(
        int(side.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        for table in ("item", "item_change", "item_review")
    )


def facet_counts(side: sqlite3.Connection, src: sqlite3.Connection) -> dict[str, Any]:
    """Counts for every derived dimension, so the filter rail only offers what exists."""
    key = _corpus_key(side)
    if _FACET_CACHE["key"] == key:
        return _FACET_CACHE["value"]

    rows = side.execute(
        "SELECT item_id, source_name, source_id, source_url, title, date_published, "
        "date_ingested, date_class, metadata_json, n_chars, is_thin FROM item"
    ).fetchall()
    built = build(side, src, rows)

    kinds: dict[str, int] = {}
    urgencies: dict[str, int] = {}
    indications: dict[str, int] = {}
    reviewed = 0
    with_change = 0
    for signal in built:
        kinds[signal["category"]] = kinds.get(signal["category"], 0) + 1
        urgencies[signal["urgency"]] = urgencies.get(signal["urgency"], 0) + 1
        name = signal["indication"] or "Indication unstated"
        indications[name] = indications.get(name, 0) + 1
        reviewed += int(signal["reviewed"])
        with_change += int(signal["what_changed"] is not None)

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    value = {
        "kinds": [
            {"name": n, "count": c} for n, c in sorted(kinds.items(), key=lambda kv: -kv[1])
        ],
        "urgencies": [
            {"name": n, "count": c} for n, c in sorted(urgencies.items(), key=lambda kv: order[kv[0]])
        ],
        "indications": [
            {"name": n, "count": c}
            for n, c in sorted(indications.items(), key=lambda kv: -kv[1])
        ],
        "reviewed_count": reviewed,
        "unreviewed_count": len(built) - reviewed,
        "with_change_count": with_change,
        "total": len(built),
    }
    _FACET_CACHE["key"], _FACET_CACHE["value"] = key, value
    return value


def invalidate_facets() -> None:
    """Called after a review write, which changes the reviewed counts."""
    _FACET_CACHE["key"] = None
