#!/usr/bin/env python3
"""inspect_data.py — Interactive or CLI viewer for ingested haemophilia papers/items.

Usage:
    python inspect_data.py                             # Interactive search/list
    python inspect_data.py --source pubmed             # List recent PubMed papers
    python inspect_data.py --search "gene therapy"    # Search by keyword in title/content
    python inspect_data.py --id 38123456               # View full details of a specific ID
    python inspect_data.py --random                    # View a random item in full detail
"""
import argparse
import asyncio
import json
import textwrap
from typing import Optional

from sqlalchemy import or_, select
from app.database import close_db, get_session, RawItemModel


def format_item(item: RawItemModel) -> str:
    """Format all details of an ingested item with clean terminal styling."""
    meta = item.metadata_dict
    meta_formatted = json.dumps(meta, indent=2, ensure_ascii=False) if meta else "None"

    divider = "=" * 80
    subdivider = "-" * 80

    lines = [
        divider,
        f"SOURCE       : {item.source_name}",
        f"ID           : {item.source_id}",
        f"TITLE        : {item.title or 'N/A'}",
        f"PUBLISHED    : {item.date_published or 'N/A'}",
        f"INGESTED     : {item.date_ingested}",
        f"URL          : {item.source_url or 'N/A'}",
        f"ACTIVE       : {item.is_active}",
        subdivider,
        "CONTENT / ABSTRACT / SUMMARY:",
        textwrap.fill(item.raw_content or "No content available.", width=80),
        subdivider,
        "METADATA (Structured JSON):",
        meta_formatted,
        divider,
    ]
    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Inspect ingested haemophilia data")
    parser.add_argument("--source", help="Filter by source name (e.g. pubmed, clinicaltrials, arxiv, edgar)")
    parser.add_argument("--search", help="Search keyword in title or content")
    parser.add_argument("--id", help="Lookup a specific source_id (e.g. PMID, NCT ID, DOI)")
    parser.add_argument("--limit", type=int, default=10, help="Number of results to display (default: 10)")
    parser.add_argument("--random", action="store_true", help="Display 1 random record with full details")
    args = parser.parse_args()

    async with get_session() as session:
        stmt = select(RawItemModel)

        if args.id:
            stmt = stmt.where(RawItemModel.source_id.ilike(f"%{args.id}%"))
        if args.source:
            stmt = stmt.where(RawItemModel.source_name.ilike(f"%{args.source}%"))
        if args.search:
            kw = f"%{args.search}%"
            stmt = stmt.where(
                or_(
                    RawItemModel.title.ilike(kw),
                    RawItemModel.raw_content.ilike(kw),
                )
            )

        if args.random:
            from sqlalchemy.sql.functions import random
            stmt = stmt.order_by(random()).limit(1)
        else:
            stmt = stmt.order_by(RawItemModel.date_ingested.desc()).limit(args.limit)

        result = await session.execute(stmt)
        items = result.scalars().all()

        if not items:
            print("No items found matching your criteria.")
            return

        for idx, item in enumerate(items, 1):
            print(f"\n[Result {idx} of {len(items)}]")
            print(format_item(item))

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
