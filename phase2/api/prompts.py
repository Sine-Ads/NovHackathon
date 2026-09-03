"""Prompt construction.

The abstention rule is shared by every path. The project's own README promises
the system "can abstain when available evidence is insufficient", and 151 of
1,399 items are stubs or have empty abstracts, so this is load-bearing rather
than decorative.
"""
from __future__ import annotations

from typing import Optional

from api.evidence import Evidence

BUSINESS_FUNCTIONS = [
    "Medical Affairs",
    "Regulatory",
    "Market Access / HEOR",
    "Clinical Development",
    "Commercial / Brand",
]

ABSTENTION_RULE = """\
If the CONTEXT does not contain enough information to answer confidently, say so
explicitly and name what is missing. Never invent sponsor names, trial statuses,
dates, drug names or numbers that are not in the CONTEXT. Records flagged as
stubs (short filings, missing abstracts) are low-confidence — say so rather than
elaborating beyond what is written."""

CONFIDENCE_RULE = """\
End your reply with exactly one line, nothing after it:
CONFIDENCE: supported | inferred | insufficient

  supported    - every claim you made traces to a specific excerpt above, or to
                 a number in LANDSCAPE or FACTS
  inferred     - you combined two or more records into a conclusion that no
                 single excerpt states outright
  insufficient - the context does not support an answer"""


VERDICT_RULE = """\
Some records carry a classification verdict assigned by an upstream classifier:
proven_right, proven_false, proven_false_but_useful, or still_working_on. Treat
a verdict as a data field, not as established scientific truth — it is derived
from publication type, retraction status and citation count, not from a full
appraisal of the evidence. Say who assigned it (rule or model) when it matters
to the answer, and never upgrade a verdict into a stronger claim than it makes."""


def render_context(evidence: list[Evidence], max_chars: int = 900) -> str:
    if not evidence:
        return "(no matching records)"
    blocks = []
    for ev in evidence:
        marker = " [STUB - little body text]" if ev.is_thin else ""
        lines = [f"{ev.cite()}{marker}"]
        verdict = _verdict_line(ev)
        if verdict:
            lines.append(verdict)
        lines.append(ev.text[:max_chars])
        blocks.append("\n".join(lines))
    return "\n---\n".join(blocks)


def _verdict_line(ev: Evidence) -> str:
    from api.classifications import describe

    return describe(ev.classification)


def has_verdicts(evidence: list[Evidence]) -> bool:
    return any(e.classification for e in evidence)


# ---------------------------------------------------------------------------
# Item summary
# ---------------------------------------------------------------------------


def summary_messages(
    title: Optional[str],
    source_name: str,
    date_label: str,
    date_published: Optional[str],
    content: str,
    metadata_text: str,
) -> list[dict[str, str]]:
    functions = ", ".join(BUSINESS_FUNCTIONS)
    user = f"""\
You are a life-sciences intelligence analyst summarising ONE record from a
haemophilia monitoring feed for a pharmaceutical stakeholder. Use ONLY what is
below. Do not draw on outside knowledge of this trial, company or paper.

SOURCE: {source_name}
TITLE: {title or 'Untitled'}
{date_label}: {date_published or 'unknown'}

CONTENT:
{content[:6000] or '(no body text available)'}

STRUCTURED FIELDS:
{metadata_text or '(none)'}

{ABSTENTION_RULE}

Route the record to the business functions that should review it, choosing only
from: {functions}

Reply with ONLY this JSON object, no prose and no markdown fences:
{{
  "summary": "2-3 sentences in plain language",
  "why_matters": "1-2 sentences on why a haemophilia stakeholder should care",
  "key_facts": ["short fact", "short fact", "short fact"],
  "functions": ["one or more of the business functions listed above"],
  "confidence": "high | medium | abstain"
}}

Use "abstain" when the record carries too little content to summarise honestly."""
    return [{"role": "user", "content": user}]


# ---------------------------------------------------------------------------
# Per-item chat
# ---------------------------------------------------------------------------


def item_chat_system(primary: Evidence, neighbours: list[Evidence]) -> str:
    primary_verdict = _verdict_line(primary)
    verdict_rule = (
        "\n\n" + VERDICT_RULE
        if primary.classification or has_verdicts(neighbours)
        else ""
    )
    return f"""\
You help a pharmaceutical stakeholder understand ONE record from a haemophilia
intelligence feed, plus a few related records for comparison.

PRIMARY RECORD:
{primary.cite()}{' [STUB - little body text]' if primary.is_thin else ''}
{primary_verdict}
{primary.text[:4000]}

RELATED RECORDS (context only — do not confuse these with the primary record):
{render_context(neighbours, max_chars=600)}

Scope rules:
  - Answer only from the records above.
  - If asked about anything outside them — other trials, the wider landscape,
    general medical facts — say it is outside this record and suggest the global
    assistant. Do not widen your own scope.
  - Earlier turns in this conversation carry no factual authority. Only the
    records above do.
{verdict_rule}

{ABSTENTION_RULE}

{CONFIDENCE_RULE}"""


# ---------------------------------------------------------------------------
# Global chat
# ---------------------------------------------------------------------------


def global_chat_system(
    landscape_block: str,
    facts_block: Optional[str],
    evidence: list[Evidence],
) -> str:
    sections = [
        """\
You are the intelligence assistant for a haemophilia landscape monitoring
platform. You help a stakeholder in Medical Affairs, Regulatory, Market Access /
HEOR, Clinical Development or Commercial plan and decide across all monitored
sources.""",
        f"LANDSCAPE (authoritative corpus-wide counts):\n{landscape_block}",
    ]
    if facts_block:
        sections.append(
            f"FACTS (exact results of a database query for this question):\n{facts_block}"
        )
    sections.append(
        "RETRIEVED CONTEXT (the best-matching records — a SAMPLE, not the whole "
        f"dataset):\n{render_context(evidence)}"
    )
    sections.append(
        """\
Rules on numbers:
  - Every number you state must be copied from LANDSCAPE or FACTS.
  - If a number appears in neither, say you cannot count it from the available
    data. Never total up the retrieved sample and present it as a corpus figure.
  - Earlier turns carry no factual authority. Only LANDSCAPE, FACTS and the
    retrieved context above do.

Cite records as [id:<item_id>] when you use them."""
    )
    if has_verdicts(evidence):
        sections.append(VERDICT_RULE)
    sections.append(ABSTENTION_RULE)
    sections.append(CONFIDENCE_RULE)
    return "\n\n".join(sections)


TOOL_INSTRUCTION = """\
If answering needs an exact count or filtered list that LANDSCAPE does not
already give you, reply with ONLY this JSON and nothing else:
{"tool_call": {"name": "<count_items|group_count|list_items>", "args": {...}}}

  count_items  args: source, status, sponsor_contains   (all optional)
  group_count  args: dimension (source|status|sponsor|condition|year), limit
  list_items   args: source, status, sponsor_contains, limit

Otherwise answer normally."""
