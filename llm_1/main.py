import asyncio
import argparse
import os
import sys

ingestion_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data-ingestion-system")
)
sys.path.insert(0, ingestion_path)
if "DATABASE_URL" not in os.environ:
    database_path = os.path.join(ingestion_path, "haemophilia_data.db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path}"

from app.database import get_active_raw_items, get_session, init_db, upsert_classification
from database_adapter import raw_item_to_scraped_paper
from llm_classifier import classify_with_llm
from paper_validator import rules_layer, validate_batch

async def load_scraped_papers():
    """Load active records from the ingestion database."""
    async with get_session() as session:
        items = await get_active_raw_items(session)
        return [raw_item_to_scraped_paper(item) for item in items]


async def save_classifications(categorised_papers, failed_classifications):
    """Persist the latest rule, LLM, and failed outcomes for frontend use."""
    await init_db()
    async with get_session() as session:
        for entry in categorised_papers:
            paper = entry["paper"]
            await upsert_classification(
                session=session,
                raw_item_id=paper["raw_item_id"],
                category=entry["category"],
                justification=entry["justification"],
                method=entry["method"],
            )
        for entry in failed_classifications:
            await upsert_classification(
                session=session,
                raw_item_id=entry["paper"]["raw_item_id"],
                category=None,
                justification=None,
                method="llm",
                reason=entry["reason"],
            )


def main(limit=None):
    scraped_papers = asyncio.run(load_scraped_papers())
    if limit is not None:
        scraped_papers = scraped_papers[:limit]

    clean_papers, rejected_records = validate_batch(scraped_papers)
    print("\n=== Validation ===")
    print(f"{len(clean_papers)} passed, {len(rejected_records)} rejected")
    for record in rejected_records:
        print(f"  Rejected: {record['record'].get('Title', '(no title)')} — {record['problems']}")

    categorised_papers = []
    uncategorised_papers = []
    for paper in clean_papers:
        result = rules_layer(paper)
        if result is None:
            uncategorised_papers.append(paper)
        else:
            categorised_papers.append({
                "paper": paper,
                "category": result,
                "justification": None,
                "method": "rule",
            })

    print("\n=== Rules layer ===")
    print(f"{len(categorised_papers)} resolved by rules, {len(uncategorised_papers)} need the LLM")

    failed_classifications = []
    for paper in uncategorised_papers:
        result = classify_with_llm(paper)
        if result["category"] is None:
            failed_classifications.append({"paper": paper, "reason": result["reason"]})
        else:
            categorised_papers.append({
                "paper": paper,
                "category": result["category"],
                "justification": result["justification"],
                "method": "llm",
            })

    print("\n=== LLM layer ===")
    print(f"{len(categorised_papers)} total categorised so far, {len(failed_classifications)} failed classification")

    print("\n=== Final results ===")
    for entry in categorised_papers:
        print(f"[{entry['method']}] {entry['paper']['title']} -> {entry['category']}")
        if entry["justification"]:
            print(f"    reason: {entry['justification']}")

    if failed_classifications:
        print("\n=== Failed to classify ===")
        for entry in failed_classifications:
            print(f"  {entry['paper']['title']} — {entry['reason']}")

    asyncio.run(save_classifications(categorised_papers, failed_classifications))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify ingested papers from the database")
    parser.add_argument("--limit", type=int, help="Maximum number of database records to classify")
    args = parser.parse_args()
    main(limit=args.limit)
