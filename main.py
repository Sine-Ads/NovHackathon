from paper_validator import validate_batch, rules_layer
from llm_classifier import classify_with_llm

# ---------------------------------------------------------------------------
# Test data — replace this with real scraped output once your teammate's
# scraper is ready. Deliberately covers every path through the pipeline:
#   - one paper that fails validation (missing fields)
#   - one paper the rules layer can resolve on its own (retracted + cited)
#   - one paper the rules layer can resolve on its own (strong RCT)
#   - one paper ambiguous enough that it needs the LLM
# ---------------------------------------------------------------------------

scraped_papers = [
    {
        # Fails validation — missing Abstract and Source entirely
        "Title": "Incomplete Scrape Example",
        "Abstract": None,
        "Source": None,
        "Publication_type": None,
        "trial_status": None,
        "retracted": None,
        "citation_count": None
    },
    {
        # Resolved by rules: retracted + cited -> proven_false_but_useful
        "Title": "Retracted Drug Trial Still Cited",
        "Abstract": "A trial of compound X later retracted due to data irregularities, but its dosing methodology was referenced in subsequent studies.",
        "Source": "pubmed",
        "Publication_type": None,
        "trial_status": "completed",
        "retracted": True,
        "citation_count": 8
    },
    {
        # Resolved by rules: strong RCT, not retracted -> proven_right
        "Title": "Large RCT Confirms Efficacy of Drug Y",
        "Abstract": "A randomized controlled trial of 4000 patients found significant improvement in outcomes.",
        "Source": "pubmed",
        "Publication_type": "RCT",
        "trial_status": "completed",
        "retracted": False,
        "citation_count": 42
    },
    {
        # Ambiguous -- no strong publication type, not retracted, not terminated,
        # not recruiting -- rules_layer() will return None, so this needs the LLM
        "Title": "Reassessment of Earlier Claims About Drug W",
        "Abstract": "Follow-up analysis found the original effect could not be replicated in a broader population, though the dataset informed later dosing studies.",
        "Source": "pubmed",
        "Publication_type": None,
        "trial_status": "completed",
        "retracted": False,
        "citation_count": 5
    },
]



clean_Paper, Rejected_record = validate_batch(scraped_papers)

print(f"\n=== Validation ===")
print(f"{len(clean_Paper)} passed, {len(Rejected_record)} rejected")
for r in Rejected_record:
    print(f"  Rejected: {r['record'].get('Title', '(no title)')} — {r['problems']}")



categorised_Paper = []
uncategorised_Paper = []

for paper in clean_Paper:
    result = rules_layer(paper)
    if result is None:
        uncategorised_Paper.append(paper)
    else:
        categorised_Paper.append({
            "paper": paper,
            "category": result,
            "justification": None,
            "method": "rule"
        })

print(f"\n=== Rules layer ===")
print(f"{len(categorised_Paper)} resolved by rules, {len(uncategorised_Paper)} need the LLM")



Failed_Classification = []

for paper in uncategorised_Paper:
    result = classify_with_llm(paper)
    if result["category"] is None:
        Failed_Classification.append({
            "paper": paper,
            "reason": result["reason"]
        })
    else:
        categorised_Paper.append({
            "paper": paper,
            "category": result["category"],
            "justification": result["justification"],
            "method": "llm"
        })

print(f"\n=== LLM layer ===")
print(f"{len(categorised_Paper)} total categorised so far, {len(Failed_Classification)} failed classification")



print(f"\n=== Final results ===")
for entry in categorised_Paper:
    print(f"[{entry['method']}] {entry['paper']['title']} -> {entry['category']}")
    if entry["justification"]:
        print(f"    reason: {entry['justification']}")

if Failed_Classification:
    print(f"\n=== Failed to classify ===")
    for entry in Failed_Classification:
        print(f"  {entry['paper']['title']} — {entry['reason']}")
