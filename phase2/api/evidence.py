"""Evidence: what was retrieved, and why.

Retrieval returns these rather than bare ids or bare strings. Every one carries
full provenance (source, identifier, permalink, date semantics) plus the reason
it surfaced, so both chatbots can justify themselves and a stakeholder can
verify any claim at its source.

``reason`` is assembled deterministically from the scoring fields. No model
writes it, so it cannot be fabricated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Date semantics differ by source, so these are the labels the UI shows instead
# of a bare date. A trial start date is not a publication event.
DATE_LABELS = {
    "publication": "Published",
    "trial_start": "Study start",
    "filing": "Filed",
    "unknown": "Date unknown",
}


@dataclass
class Evidence:
    """One retrieved unit, with provenance and a scoring trail."""

    chunk_id: str
    item_id: str
    source_name: str
    source_id: str
    source_url: Optional[str] = None
    title: Optional[str] = None
    date_published: Optional[str] = None
    date_class: str = "unknown"

    # why it surfaced
    matched_by: list[str] = field(default_factory=list)
    fts_rank: Optional[int] = None
    vec_rank: Optional[int] = None
    vec_score: Optional[float] = None
    rrf_score: float = 0.0
    evidence_score: float = 0.0
    completeness: float = 1.0
    recency: float = 1.0

    n_chars: int = 0
    is_thin: bool = False
    text: str = ""
    reason: str = ""

    # Phase 1's classifier verdict, when one exists. Read live rather than
    # indexed, so re-running the classifier is reflected immediately.
    classification: Optional[dict] = None

    @property
    def date_label(self) -> str:
        return DATE_LABELS.get(self.date_class, "Date unknown")

    def to_dict(self, include_text: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data["date_label"] = self.date_label
        if not include_text:
            data.pop("text", None)
        return data

    def cite(self) -> str:
        """Compact context header handed to the LLM."""
        date = self.date_published[:10] if self.date_published else "unknown"
        verdict = ""
        if self.classification and self.classification.get("category"):
            verdict = f" | verdict: {self.classification['category']}"
        return (
            f"[{self.source_name} | {self.title or 'Untitled'} | "
            f"{self.date_label}: {date}{verdict} | id:{self.item_id}]"
        )


# ---------------------------------------------------------------------------
# Evidence ranking — the layer between search and intelligence
# ---------------------------------------------------------------------------


def completeness_factor(n_chars: int, is_thin: bool) -> float:
    """Down-weight records with little to say.

    A 154-character SEC stub can still be the right answer, so this never zeroes
    a result — it only stops one winning a near-tie against a full record.
    """
    if is_thin or n_chars < 150:
        return 0.60
    if n_chars < 400:
        return 0.85
    return 1.00


def recency_factor(date_published: Optional[str], date_class: str) -> float:
    """A bounded nudge toward recent material.

    Applied only where the date is a genuine publication or filing event.
    ClinicalTrials.gov stores a study *start* date — 9 rows are dated into 2027 —
    so trials are held neutral rather than rewarded for a date they have not
    reached. The +/-10% range is narrower than typical gaps between adjacent RRF
    ranks: recency breaks ties, it never overrides relevance.
    """
    if date_class not in ("publication", "filing") or not date_published:
        return 1.00
    try:
        parsed = datetime.fromisoformat(date_published.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(date_published[:10], "%Y-%m-%d")
        except ValueError:
            return 1.00
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_years = (datetime.now(timezone.utc) - parsed).days / 365.25
    return max(0.90, min(1.10, 1.10 - 0.04 * age_years))


def build_reason(ev: Evidence) -> str:
    """Plain-language account of why this item surfaced. Deterministic."""
    parts: list[str] = []
    if ev.fts_rank is not None and ev.vec_rank is not None:
        parts.append(
            f"matched on both keyword (#{ev.fts_rank}) and meaning "
            f"(#{ev.vec_rank}, similarity {ev.vec_score:.2f})"
        )
    elif ev.fts_rank is not None:
        parts.append(f"keyword match (#{ev.fts_rank})")
    elif ev.vec_rank is not None:
        parts.append(f"semantic match (#{ev.vec_rank}, similarity {ev.vec_score:.2f})")
    else:
        parts.append("related by similarity")

    if ev.is_thin:
        parts.append("record is a stub with little body text, so it is ranked lower")
    elif ev.completeness < 1.0:
        parts.append("short record, ranked slightly lower")

    if ev.recency > 1.0:
        parts.append("recent, ranked slightly higher")
    elif ev.recency < 1.0:
        parts.append("older, ranked slightly lower")

    return "; ".join(parts)


def rank(evidence: list[Evidence]) -> list[Evidence]:
    """Apply completeness and recency, then sort. Relevance stays dominant."""
    for ev in evidence:
        ev.completeness = completeness_factor(ev.n_chars, ev.is_thin)
        ev.recency = recency_factor(ev.date_published, ev.date_class)
        ev.evidence_score = ev.rrf_score * ev.completeness * ev.recency
        ev.reason = build_reason(ev)
    evidence.sort(key=lambda e: e.evidence_score, reverse=True)
    return evidence
