"""Answer confidence for chat.

A global assistant that sounds equally certain about a quoted trial status and a
three-document inference is worse than useless for someone making a decision.
Every answer therefore carries one of three levels.

Confidence is not the model's to award itself. Deterministic gates run before
generation and can force a level down; validation after generation can lower a
claim but never raise it.
"""
from __future__ import annotations

import re
from typing import Optional

from api.config import MIN_EVIDENCE
from api.evidence import Evidence
from api.router import Route

SUPPORTED = "supported"
INFERRED = "inferred"
INSUFFICIENT = "insufficient"
LEVELS = (SUPPORTED, INFERRED, INSUFFICIENT)

_CONFIDENCE_LINE = re.compile(
    r"^\s*CONFIDENCE\s*:\s*(supported|inferred|insufficient)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CITATION = re.compile(r"\[id:([^\]]+)\]")


def gate(evidence: list[Evidence], route: Route = Route.RETRIEVAL) -> Optional[str]:
    """Decide before calling the model whether an answer is possible at all.

    Returning ``INSUFFICIENT`` short-circuits generation entirely: no LLM call,
    no latency, and nothing that could hallucinate.
    """
    if route is Route.AGGREGATE:
        # FACTS come from SQL over the whole corpus and are exact by
        # construction, so thin retrieval is irrelevant here.
        return None
    if not evidence:
        return INSUFFICIENT
    if max(e.evidence_score for e in evidence) < MIN_EVIDENCE:
        return INSUFFICIENT
    if all(e.is_thin for e in evidence):
        return INSUFFICIENT
    return None


def insufficient_message(query: str, evidence: list[Evidence], scope: str) -> str:
    """Templated reply used when the gate declines. States what was searched."""
    if scope == "item":
        return (
            "I can't answer that from this record or the ones related to it. "
            "The question looks like it needs information this record does not "
            "carry — try the global assistant, which searches the whole corpus."
        )
    if not evidence:
        return (
            f"I found no records matching that in the monitored corpus, so I can't "
            "answer it. The corpus covers clinical trial registrations, published "
            "literature, preprints and SEC filings on haemophilia — it holds no "
            "pricing, reimbursement, HTA or regulatory-approval data."
        )
    sources = sorted({e.source_name for e in evidence})
    return (
        "I don't have enough evidence to answer that confidently. The closest "
        f"records ({', '.join(sources)}) are stubs or only loosely related, and "
        "I'd be guessing if I answered from them. You can open the sources below "
        "to judge for yourself."
    )


def parse_and_strip(text: str) -> tuple[str, Optional[str]]:
    """Pull the model's CONFIDENCE line off the end of its answer."""
    match = None
    for match in _CONFIDENCE_LINE.finditer(text):
        pass  # keep the last occurrence
    if not match:
        return text.strip(), None
    claimed = match.group(1).lower()
    cleaned = (text[: match.start()] + text[match.end() :]).strip()
    return cleaned, claimed


def validate(
    answer: str,
    claimed: Optional[str],
    evidence: list[Evidence],
    route: Route = Route.RETRIEVAL,
) -> tuple[str, list[str]]:
    """Settle the final confidence level and the citation list.

    The model may lower its own confidence; it may not raise it past what the
    evidence supports. A ``supported`` claim with no citations, or citing ids
    that were never retrieved, is demoted.
    """
    available = {e.item_id for e in evidence}
    cited = [c for c in _CITATION.findall(answer) if c in available]

    level = claimed if claimed in LEVELS else INFERRED

    if route is Route.AGGREGATE:
        # The numbers came from SQL, so a supported claim stands on its own.
        return level, cited

    if level == SUPPORTED and not cited:
        level = INFERRED
    if level == SUPPORTED and any(c not in available for c in _CITATION.findall(answer)):
        level = INFERRED
    if not evidence:
        level = INSUFFICIENT

    return level, cited


def strip_bad_citations(answer: str, evidence: list[Evidence]) -> str:
    """Remove citation markers pointing at records that were never retrieved."""
    available = {e.item_id for e in evidence}
    return _CITATION.sub(
        lambda m: m.group(0) if m.group(1) in available else "", answer
    )
