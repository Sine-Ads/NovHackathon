"""Turning a Phase 1 row into indexable text.

Two jobs:

``flatten_metadata`` folds each source's structured metadata into searchable
text, because stakeholders search for sponsors, conditions, journals and company
names — none of which live in ``raw_content``. Every source stores a different
shape, so the branching here is unavoidable and is the single place it happens.

``chunk_item`` splits an item into embedding units. Today it returns exactly one
chunk: the corpus averages ~1.2k characters and only a handful of
ClinicalTrials.gov descriptions exceed 4k. Everything downstream is already
chunk-keyed, so swapping this for a sliding-window splitter when long documents
arrive changes nothing outside this file.
"""
from __future__ import annotations

import hashlib
from typing import Any

from api.source_db import SourceItem

# Beyond this, a single chunk stops being a sensible embedding unit. Only a few
# ClinicalTrials.gov detailed descriptions reach it today.
MAX_CHUNK_CHARS = 8_000


def _join(values: Any) -> str:
    """Metadata values are variously a list, a string, or None across sources."""
    if values is None:
        return ""
    if isinstance(values, (list, tuple)):
        return ", ".join(str(v) for v in values if v)
    return str(values)


def flatten_metadata(item: SourceItem) -> str:
    """Render source-specific metadata as searchable text."""
    meta = item.metadata
    source = item.source_name
    parts: list[str] = []

    if source == "ClinicalTrials.gov":
        parts += [
            f"Status: {_join(meta.get('overall_status'))}",
            f"Sponsor: {_join(meta.get('lead_sponsor'))}",
            f"Conditions: {_join(meta.get('conditions'))}",
            f"Interventions: {_join(meta.get('interventions'))}",
        ]
    elif source == "PubMed (NCBI)":
        parts += [
            f"Journal: {_join(meta.get('journal'))}",
            f"Authors: {_join(meta.get('authors'))}",
            f"MeSH terms: {_join(meta.get('mesh_terms'))}",
        ]
    elif source == "SEC EDGAR":
        parts += [
            f"Company: {_join(meta.get('company_name'))}",
            f"Form: {_join(meta.get('form'))}",
            f"Period ending: {_join(meta.get('period_ending'))}",
        ]
    elif source in ("arXiv", "medRxiv"):
        parts += [
            f"Authors: {_join(meta.get('authors'))}",
            f"Categories: {_join(meta.get('categories') or meta.get('category'))}",
        ]
    elif source == "OpenFDA":
        # One source_name carries two record shapes, told apart by metadata.type.
        if meta.get("type") == "drug_recall":
            parts += [
                f"Recall: {_join(meta.get('recall_number'))}",
                f"Classification: {_join(meta.get('classification'))}",
                f"Firm: {_join(meta.get('recalling_firm'))}",
                f"Reason: {_join(meta.get('reason_for_recall'))}",
            ]
        else:
            parts += [
                f"Drugs: {_join(meta.get('drugs'))}",
                f"Reactions: {_join(meta.get('reactions'))}",
                f"Indications: {_join(meta.get('indications'))}",
            ]
    elif source == "USPTO Patents":
        parts += [f"Applicant: {_join(meta.get('applicant'))}"]
    elif source == "WHO ICTRP":
        parts += [
            f"Status: {_join(meta.get('recruitment_status'))}",
            f"Condition: {_join(meta.get('condition'))}",
            f"Intervention: {_join(meta.get('intervention'))}",
            f"Sponsor: {_join(meta.get('primary_sponsor'))}",
            f"Countries: {_join(meta.get('countries'))}",
        ]

    return "\n".join(p for p in parts if not p.endswith(": "))


def identifiers(item: SourceItem) -> str:
    """Every identifier a stakeholder might paste into the search box.

    Without this, searching an NCT number, PMID or DOI returns nothing: the
    identifier lives in a metadata field, not in the body text.
    """
    values = [item.source_id]
    for key in ("nct_id", "pmid", "doi", "arxiv_id", "trial_id", "adsh",
                "recall_number", "safetyreportid", "application_number"):
        value = item.metadata.get(key)
        if value:
            values.append(str(value))
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return " ".join(seen)


def build_body(item: SourceItem) -> str:
    """The full indexable text for an item: title, content, metadata, identifiers."""
    segments = [
        item.title or "",
        item.raw_content or "",
        flatten_metadata(item),
        identifiers(item),
    ]
    return "\n\n".join(s for s in segments if s.strip()).strip()


def content_hash(item: SourceItem) -> str:
    """Fingerprint of everything indexing depends on.

    Drives both idempotent reindexing and summary-cache invalidation, so it must
    cover the metadata as well as the text.
    """
    return hashlib.sha256(build_body(item).encode("utf-8")).hexdigest()


def chunk_item(item: SourceItem) -> list[tuple[str, str]]:
    """Return [(chunk_id, text)] for an item.

    One chunk per item today. When long documents arrive, split here and return
    several — retrieval already rolls chunks up to items, so nothing else moves.
    """
    body = build_body(item)
    if not body:
        body = item.title or item.source_id
    return [(f"{item.item_id}:0", body[:MAX_CHUNK_CHARS])]
