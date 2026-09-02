"""Map ingestion database records to the classifier input contract."""


def raw_item_to_scraped_paper(item):
    """Map a database row into the validator's existing input contract."""
    metadata = item.metadata_dict
    return {
        "raw_item_id": item.id,
        "Title": item.title,
        "Abstract": item.raw_content,
        "Source": item.source_name,
        "Publication_type": metadata.get("publication_type", "unknown"),
        "trial_status": metadata.get("trial_status")
        or metadata.get("overall_status", "unknown"),
        "retracted": bool(metadata.get("retracted", False)),
        "citation_count": metadata.get("citation_count", 0),
    }