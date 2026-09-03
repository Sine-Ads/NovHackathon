"""
test_rules_layer.py

Manual test script for rules_layer() from paper_validator.py.
Run this directly: python3 test_rules_layer.py

Each test case is designed to trigger ONE specific branch. Compare the
printed "Got" against "Expected" for each — don't just eyeball it.
"""

from paper_validator import rules_layer

# Branch 1: retracted + has citations -> proven_false_but_useful
test_1 = {
    "retracted": True,
    "citation_count": 5,
    "trial_status": None,
    "publication_type": None,
}

# Branch 2: retracted + no citations -> proven_false
test_2 = {
    "retracted": True,
    "citation_count": 0,
    "trial_status": None,
    "publication_type": None,
}

# Branch 3: trial terminated -> proven_false
test_3 = {
    "retracted": False,
    "citation_count": 0,
    "trial_status": "terminated",
    "publication_type": None,
}

# Branch 4: strong publication type -> proven_right
test_4 = {
    "retracted": False,
    "citation_count": 0,
    "trial_status": None,
    "publication_type": "RCT",
}

# Branch 5: early-stage -> still_working_on
test_5 = {
    "retracted": False,
    "citation_count": 0,
    "trial_status": None,
    "publication_type": "preprint",
}

# Branch 6: nothing matches -> None
test_6 = {
    "retracted": False,
    "citation_count": 0,
    "trial_status": None,
    "publication_type": None,
}

# TRAP CASE: retracted=True AND publication_type="RCT" set at the same time.
# Predict the result yourself before running this — which branch actually
# fires first, given the elif chain runs top to bottom?
test_trap = {
    "retracted": True,
    "citation_count": 5,
    "trial_status": None,
    "publication_type": "RCT",
}

cases = [
    ("test_1 (retracted + cited)", test_1, "proven_false_but_useful"),
    ("test_2 (retracted, no citations)", test_2, "proven_false"),
    ("test_3 (terminated trial)", test_3, "proven_false"),
    ("test_4 (RCT)", test_4, "proven_right"),
    ("test_5 (preprint)", test_5, "still_working_on"),
    ("test_6 (nothing matches)", test_6, None),
    ("test_trap (retracted AND RCT both true)", test_trap, "???"),  # predict this yourself first
]

for name, paper, expected in cases:
    got = rules_layer(paper)
    match = "OK" if got == expected else "MISMATCH"
    print(f"{name}: expected={expected!r}, got={got!r}  [{match}]")
