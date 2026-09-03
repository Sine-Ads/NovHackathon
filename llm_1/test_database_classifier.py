from types import SimpleNamespace

from database_adapter import raw_item_to_scraped_paper


def test_raw_item_to_scraped_paper_maps_database_fields():
    item = SimpleNamespace(
        id="raw-item-1",
        title="A study",
        raw_content="Study abstract",
        source_name="PubMed (NCBI)",
        metadata_dict={"overall_status": "COMPLETED", "citation_count": 3},
    )

    assert raw_item_to_scraped_paper(item) == {
        "raw_item_id": "raw-item-1",
        "Title": "A study",
        "Abstract": "Study abstract",
        "Source": "PubMed (NCBI)",
        "Publication_type": "unknown",
        "trial_status": "COMPLETED",
        "retracted": False,
        "citation_count": 3,
    }