
required = ["Title", "Abstract", "Source", "trial_status", "retracted"]
 
optional_with_defaults = {
    "Publication_type": "unknown",
    "citation_count": 0
}
 
 
def validate_batch(scraped_papers):
    """Takes a list of raw scraped paper dicts. Returns (clean_Paper, Rejected_record) —
    clean_Paper is a list of validated, normalized paper dicts ready for classification.
    Rejected_record is a list of {"record": ..., "problems": [...]} for anything that failed."""
 
    clean_Paper = []
    Rejected_record = []
 
    for Paper_Category in scraped_papers:
        problems = []
        for key in required:
            if key in Paper_Category:
                value = Paper_Category[key]
                if value is None:
                    problems.append(f"{key} exists but is empty/None")
            else:
                problems.append(f"{key} is missing")
 
        if not problems:
            Paper = {
                "raw_item_id": Paper_Category.get("raw_item_id"),
                "title": Paper_Category["Title"],
                "abstract": Paper_Category["Abstract"],
                "source": Paper_Category["Source"],
                "publication_type": Paper_Category.get("Publication_type") or optional_with_defaults["Publication_type"],
                "trial_status": Paper_Category["trial_status"],
                "retracted": Paper_Category["retracted"],
                "citation_count": Paper_Category.get("citation_count") if Paper_Category.get("citation_count") is not None else optional_with_defaults["citation_count"]
            }
            clean_Paper.append(Paper)
        else:
            Rejected_record.append({"record": Paper_Category, "problems": problems})
 
    return clean_Paper, Rejected_record
 
 
def rules_layer(clean_Paper):
    # ClinicalTrials.gov reports status as an uppercase enum (TERMINATED,
    # RECRUITING). The comparisons below are written in lowercase, so without
    # normalising here no trial-status rule can ever fire and every trial
    # falls through to the LLM.
    trial_status = (clean_Paper.get("trial_status") or "").strip().lower()
    if clean_Paper.get("retracted") and clean_Paper.get("citation_count") > 0:
        return "proven_false_but_useful"
    elif clean_Paper.get("retracted") and clean_Paper.get("citation_count") == 0:
        return "proven_false"
    elif trial_status == "terminated":
        return "proven_false"
    elif clean_Paper.get("publication_type") == "meta_analysis" or clean_Paper.get("publication_type") == "systematic_review" or clean_Paper.get("publication_type") == "RCT":
        return "proven_right"
    elif clean_Paper.get("publication_type") == "case_report" or clean_Paper.get("publication_type") == "preprint" or trial_status == "recruiting":
        return "still_working_on"
    else:
        return None
 
 
if __name__ == "__main__":
    # Quick manual test — only runs when you execute this file directly,
    # not when another file imports validate_batch or rules_layer from it.
    test_papers = [{
        "Title": "TestPaper123",
        "Abstract": None,
        "Source": None,
        "Publication_type": None,
        "trial_status": None,
        "retracted": None,
        "citation_count": None
    }]
    clean, rejected = validate_batch(test_papers)
    print("Clean papers:", clean)
    print("Rejected records:", rejected)
 
