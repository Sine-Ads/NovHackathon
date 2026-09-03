"""Intent routing for the global assistant.

Aggregate questions are not a special case bolted onto retrieval — they are one
of three first-class paths. Top-k retrieval sees eight documents and physically
cannot answer "how many trials are recruiting"; the aggregate path runs SQL over
all 1,399 rows instead.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class Route(str, Enum):
    AGGREGATE = "aggregate"   # counting, ranking, distribution
    RETRIEVAL = "retrieval"   # qualitative, topical
    BOTH = "both"             # comparison, planning


_COUNTING = re.compile(
    r"\b(how many|how much|number of|count|total|tally|"
    r"most|least|top|largest|biggest|leading|rank|ranked|ranking|"
    r"distribution|breakdown|proportion|share|percentage|"
    r"trend|over time|by year|list all|all of the|every)\b",
    re.IGNORECASE,
)

_TOPICAL = re.compile(
    r"\b(what|why|how does|how do|explain|describe|summar|tell me about|"
    r"compare|versus|vs\.?|implication|mean for|should we|recommend|plan|"
    r"watch|risk|opportunity|evidence|finding|result)\b",
    re.IGNORECASE,
)


def route(question: str) -> Route:
    """Pick the context-assembly path for a question."""
    text = question or ""
    counting = bool(_COUNTING.search(text))
    topical = bool(_TOPICAL.search(text))

    if counting and topical:
        return Route.BOTH
    if counting:
        return Route.AGGREGATE
    return Route.RETRIEVAL


def suggest_aggregate(question: str) -> Optional[dict]:
    """Guess a whitelisted aggregate directly from the wording.

    Saves an LLM round-trip on the common phrasings. Returning None simply means
    the model is asked to choose a query itself.
    """
    text = (question or "").lower()

    if re.search(r"\b(sponsor|company|companies|funder)\b", text):
        return {"name": "group_count", "args": {"dimension": "sponsor", "limit": 15}}
    if re.search(r"\b(status|recruiting|completed|terminated|withdrawn|ongoing)\b", text):
        return {"name": "group_count", "args": {"dimension": "status", "limit": 15}}
    if re.search(r"\b(condition|indication|disease)\b", text):
        return {"name": "group_count", "args": {"dimension": "condition", "limit": 12}}
    if re.search(r"\b(source|where.*from|which database)\b", text):
        return {"name": "group_count", "args": {"dimension": "source", "limit": 10}}
    if re.search(r"\b(year|over time|trend|timeline)\b", text):
        return {"name": "group_count", "args": {"dimension": "year", "limit": 15}}
    return None
