"""On-demand item summaries, cached after the first expansion.

Thin records never reach the model. All 100 SEC EDGAR rows are 154-character
index pointers and 51 PubMed rows have no abstract; asking a model to summarise
those produces confident fiction. They get a template built from the structured
metadata instead, marked ``abstain`` — which is also faster and free.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from api import chunker, llm, store
from api.config import LLM_MODEL, THIN_CONTENT_CHARS
from api.evidence import DATE_LABELS
from api.prompts import BUSINESS_FUNCTIONS, summary_messages
from api.source_db import SourceItem

# Which teams care about which source, when we cannot ask the model.
DEFAULT_FUNCTIONS = {
    "ClinicalTrials.gov": ["Clinical Development", "Medical Affairs"],
    "PubMed (NCBI)": ["Medical Affairs"],
    "arXiv": ["Medical Affairs"],
    "medRxiv": ["Medical Affairs"],
    "SEC EDGAR": ["Commercial / Brand", "Market Access / HEOR"],
    "OpenFDA": ["Regulatory"],
    "USPTO Patents": ["Commercial / Brand"],
    "WHO ICTRP": ["Clinical Development"],
}


def is_thin(item: SourceItem) -> bool:
    return (
        len(item.raw_content or "") < THIN_CONTENT_CHARS
        or item.source_name == "SEC EDGAR"
    )


def _key_facts(item: SourceItem) -> list[str]:
    """Facts drawn straight from structured metadata — no model involved."""
    meta = item.metadata
    facts: list[str] = []

    def add(label: str, value: Any) -> None:
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value if v)
        if value:
            facts.append(f"{label}: {value}")

    if item.source_name == "ClinicalTrials.gov":
        add("Registry ID", meta.get("nct_id"))
        add("Status", meta.get("overall_status"))
        add("Sponsor", meta.get("lead_sponsor"))
        add("Conditions", meta.get("conditions"))
        add("Interventions", meta.get("interventions"))
    elif item.source_name == "PubMed (NCBI)":
        add("PMID", meta.get("pmid"))
        add("Journal", meta.get("journal"))
        add("Authors", (meta.get("authors") or [])[:4])
        add("DOI", meta.get("doi"))
    elif item.source_name == "SEC EDGAR":
        add("Company", meta.get("company_name"))
        add("Form", meta.get("form"))
        add("Filed", meta.get("file_date"))
        add("Period ending", meta.get("period_ending"))
    elif item.source_name in ("arXiv", "medRxiv"):
        add("Authors", (meta.get("authors") or [])[:4] if isinstance(meta.get("authors"), list) else meta.get("authors"))
        add("Categories", meta.get("categories") or meta.get("category"))
        add("DOI", meta.get("doi"))
    elif item.source_name == "OpenFDA":
        if meta.get("type") == "drug_recall":
            add("Recall", meta.get("recall_number"))
            add("Classification", meta.get("classification"))
            add("Firm", meta.get("recalling_firm"))
            add("Reason", meta.get("reason_for_recall"))
        else:
            add("Report", meta.get("safetyreportid"))
            add("Drugs", meta.get("drugs"))
            add("Reactions", meta.get("reactions"))
    elif item.source_name == "WHO ICTRP":
        add("Trial ID", meta.get("trial_id"))
        add("Status", meta.get("recruitment_status"))
        add("Sponsor", meta.get("primary_sponsor"))
        add("Countries", meta.get("countries"))
    elif item.source_name == "USPTO Patents":
        add("Application", meta.get("application_number"))
        add("Applicant", meta.get("applicant"))

    return facts[:6]


def _template_summary(item: SourceItem) -> dict[str, Any]:
    """The honest answer for a record with no body text."""
    meta = item.metadata
    if item.source_name == "SEC EDGAR":
        text = (
            f"This is an index record for a {meta.get('form', 'filing')} by "
            f"{meta.get('company_name', 'the filer')} that mentions haemophilia. "
            "The ingestion pipeline stored the filing reference and matching "
            "excerpt only, not the filing text, so there is nothing here to "
            "summarise in depth."
        )
        why = (
            "It tells you which companies are discussing haemophilia in their "
            "regulatory disclosures. Open the filing at the source to read it."
        )
    else:
        text = (
            f"This {item.source_name} record was captured without body text — "
            "the source provided a title and metadata but no abstract or "
            "description. There is not enough content to summarise."
        )
        why = "Open the record at its source to judge relevance."

    return {
        "summary": text,
        "why_matters": why,
        "key_facts": _key_facts(item),
        "functions": DEFAULT_FUNCTIONS.get(item.source_name, ["Medical Affairs"]),
        "confidence": "abstain",
    }


def summarize(
    side: sqlite3.Connection, item: SourceItem, force: bool = False
) -> dict[str, Any]:
    """Return a summary, from cache when possible."""
    digest = chunker.content_hash(item)

    if not force:
        cached = store.get_summary(side, item.item_id, digest)
        if cached:
            cached["cached"] = True
            return cached

    if is_thin(item):
        payload = _template_summary(item)
        store.put_summary(side, item.item_id, digest, "template", payload)
        payload["cached"] = False
        return payload

    date_label = DATE_LABELS.get(item.date_class, "Date")
    messages = summary_messages(
        title=item.title,
        source_name=item.source_name,
        date_label=date_label,
        date_published=item.date_published,
        content=item.raw_content or "",
        metadata_text=chunker.flatten_metadata(item),
    )

    try:
        parsed = llm.complete_json(messages, max_tokens=600)
    except llm.LLMUnavailable as exc:
        # Never cache a failure — a later retry should be able to succeed.
        return {
            "summary": None,
            "why_matters": None,
            "key_facts": _key_facts(item),
            "functions": DEFAULT_FUNCTIONS.get(item.source_name, []),
            "confidence": "abstain",
            "cached": False,
            "error": str(exc),
        }

    if not parsed:
        payload = _template_summary(item)
        payload["summary"] = (
            "The summarisation model did not return a usable response for this "
            "record. The structured facts below come straight from the source."
        )
        return {**payload, "cached": False}

    valid = set(BUSINESS_FUNCTIONS)
    payload = {
        "summary": parsed.get("summary"),
        "why_matters": parsed.get("why_matters"),
        "key_facts": [str(f) for f in (parsed.get("key_facts") or [])][:6]
        or _key_facts(item),
        "functions": [f for f in (parsed.get("functions") or []) if f in valid]
        or DEFAULT_FUNCTIONS.get(item.source_name, []),
        "confidence": parsed.get("confidence")
        if parsed.get("confidence") in ("high", "medium", "abstain")
        else "medium",
    }
    store.put_summary(side, item.item_id, digest, LLM_MODEL, payload)
    payload["cached"] = False
    return payload
