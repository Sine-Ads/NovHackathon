"""Corpus-wide statistics, computed deterministically.

Every number the global assistant states comes from here or from
``aggregates.py``. The model is never asked to count, because top-k retrieval
sees eight documents and would have to guess — confidently and wrongly.

Condition and sponsor labels are normalised before counting. Reporting
"Hemophilia A: 361" when the merged British/American spellings total 444 is
exactly the quiet error that destroys trust in an intelligence tool.
"""
from __future__ import annotations

import collections
import re
import sqlite3
from typing import Any

from api import source_db
from api.config import THIN_CONTENT_CHARS


def normalize_condition(text: str) -> str:
    """Fold spelling variants so counts mean something.

    'Haemophilia A' and 'Hemophilia A' are the same condition; the corpus
    carries 83 of the first and 361 of the second.
    """
    out = text.strip().lower()
    out = out.replace("haemophilia", "hemophilia")
    out = re.sub(r"\s+", " ", out)
    return out.title()


def normalize_sponsor(name: str) -> str:
    """Collapse the corporate-history suffixes the registry carries.

    'Baxalta now part of Shire' and 'Wyeth is now a wholly owned subsidiary of
    Pfizer' are distinct strings for what a stakeholder reads as one sponsor.
    """
    out = name.strip()
    out = re.sub(
        r"\s+(now part of|is now a wholly owned subsidiary of|now|a subsidiary of)\s+.*$",
        "",
        out,
        flags=re.IGNORECASE,
    )
    return out.strip(" .,") or name.strip()


def compute(conn: sqlite3.Connection) -> dict[str, Any]:
    """Aggregate the whole corpus. Cheap enough to run synchronously."""
    by_source: collections.Counter = collections.Counter()
    status: collections.Counter = collections.Counter()
    sponsors: collections.Counter = collections.Counter()
    conditions: collections.Counter = collections.Counter()
    forms: collections.Counter = collections.Counter()
    companies: collections.Counter = collections.Counter()
    openfda_types: collections.Counter = collections.Counter()

    total = 0
    thin = 0
    undated = 0
    trials_without_interventions = 0
    years: collections.Counter = collections.Counter()

    for item in source_db.iter_items(conn):
        total += 1
        by_source[item.source_name] += 1
        if not (item.raw_content or "") or len(item.raw_content or "") < THIN_CONTENT_CHARS:
            thin += 1
        if not item.date_published:
            undated += 1
        else:
            years[item.date_published[:4]] += 1

        meta = item.metadata
        if item.source_name == "ClinicalTrials.gov":
            if not meta.get("interventions"):
                trials_without_interventions += 1
            if meta.get("overall_status"):
                status[meta["overall_status"]] += 1
            if meta.get("lead_sponsor"):
                sponsors[normalize_sponsor(meta["lead_sponsor"])] += 1
            for cond in meta.get("conditions") or []:
                conditions[normalize_condition(cond)] += 1
        elif item.source_name == "SEC EDGAR":
            if meta.get("form"):
                forms[meta["form"]] += 1
            if meta.get("company_name"):
                companies[meta["company_name"]] += 1
        elif item.source_name == "OpenFDA":
            openfda_types[meta.get("type", "unknown")] += 1

    # Known coverage gaps. Stating these in the prompt is what lets the
    # assistant decline honestly instead of inventing an answer.
    caveats = []
    if undated:
        caveats.append(
            f"{undated} of {total} items have no publication date and cannot be placed on a timeline."
        )
    if thin:
        caveats.append(
            f"{thin} items are stubs with little or no body text (SEC EDGAR rows are "
            "index pointers, not full filings) and cannot be summarised in depth."
        )
    if trials_without_interventions:
        caveats.append(
            f"No intervention/drug names were captured for {trials_without_interventions} "
            "clinical trials, so the corpus cannot answer which drug a trial used."
        )
    caveats.append(
        "Dates mean different things by source: study start for trials, publication "
        "date for papers, filing date for SEC records."
    )
    caveats.append(
        "The corpus covers clinical trials, literature, preprints and SEC filings only. "
        "It holds no pricing, reimbursement, HTA or regulatory-approval data."
    )

    from api import classifications

    verdicts = classifications.counts(conn)
    if verdicts["available"]:
        if verdicts["unclassified"]:
            caveats.append(
                f"{verdicts['unclassified']} records carry no classifier verdict yet; "
                "absence of a verdict is not a negative verdict."
            )
        if verdicts["failed"]:
            caveats.append(
                f"The classifier failed on {verdicts['failed']} records — those are "
                "unclassified, not disproven."
            )

    return {
        "total_items": total,
        "by_source": dict(by_source.most_common()),
        "classifications": verdicts,
        "trial_status": dict(status.most_common()),
        "top_sponsors": sponsors.most_common(15),
        "top_conditions": conditions.most_common(12),
        "sec_forms": dict(forms.most_common()),
        "top_sec_companies": companies.most_common(8),
        "openfda_types": dict(openfda_types),
        "items_by_year": dict(sorted(years.items(), reverse=True)[:12]),
        "undated_items": undated,
        "thin_items": thin,
        "caveats": caveats,
    }


def to_prompt_block(stats: dict[str, Any]) -> str:
    """Render the stats compactly for a system prompt (~600 tokens)."""
    lines = [f"Total items monitored: {stats['total_items']}"]
    lines.append(
        "By source: "
        + ", ".join(f"{k} {v}" for k, v in stats["by_source"].items())
    )
    if stats["trial_status"]:
        lines.append(
            "Clinical trial status counts: "
            + ", ".join(f"{k} {v}" for k, v in stats["trial_status"].items())
        )
    if stats["top_sponsors"]:
        lines.append(
            "Most active trial sponsors: "
            + ", ".join(f"{k} ({v})" for k, v in stats["top_sponsors"][:10])
        )
    if stats["top_conditions"]:
        lines.append(
            "Most frequent conditions (spelling variants merged): "
            + ", ".join(f"{k} ({v})" for k, v in stats["top_conditions"][:8])
        )
    if stats["sec_forms"]:
        lines.append(
            "SEC filing forms: "
            + ", ".join(f"{k} {v}" for k, v in stats["sec_forms"].items())
        )
    if stats.get("top_sec_companies"):
        lines.append(
            "Companies in SEC filings: "
            + ", ".join(f"{k} ({v})" for k, v in stats["top_sec_companies"][:6])
        )
    verdicts = stats.get("classifications") or {}
    if verdicts.get("available") and verdicts.get("by_category"):
        lines.append(
            "Classifier verdicts: "
            + ", ".join(f"{k} {v}" for k, v in verdicts["by_category"].items())
            + f" ({verdicts.get('unclassified', 0)} records not yet classified"
            + (f", {verdicts['failed']} failed" if verdicts.get("failed") else "")
            + ")"
        )
    lines.append("")
    lines.append("Known coverage limits:")
    for caveat in stats["caveats"]:
        lines.append(f"  - {caveat}")
    return "\n".join(lines)
