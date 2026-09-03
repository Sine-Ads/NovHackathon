#!/usr/bin/env python3
"""Golden-question evaluation for the Phase 2 assistants.

Smoke tests prove the API responds. This proves the answers are right — and,
just as importantly, that the system declines when it should.

Requires the API running on port 8000 and HF_TOKEN configured.

Usage:
    python scripts/run_eval.py
    python scripts/run_eval.py --only insufficient_pricing
    python scripts/run_eval.py --category insufficient_evidence
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

API = "http://localhost:8000"
GOLDEN = Path(__file__).resolve().parent.parent / "eval" / "golden.yaml"
CITATION = re.compile(r"\[id:([^\]]+)\]")


def stream_chat(path: str, payload: dict) -> dict:
    """POST to an SSE endpoint and collect the whole exchange."""
    request = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    answer, evidence, confidence = [], [], None
    route, facts, citations = None, None, []

    with urllib.request.urlopen(request, timeout=180) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            kind = event.get("type")
            if kind == "evidence":
                evidence = event.get("evidence", [])
                route = event.get("route")
                facts = event.get("facts")
            elif kind == "facts":
                facts = event.get("facts")
            elif kind == "delta":
                answer.append(event.get("text", ""))
            elif kind == "done":
                confidence = event.get("confidence")
                citations = event.get("citations", [])

    return {
        "answer": "".join(answer),
        "evidence": evidence,
        "confidence": confidence,
        "route": route,
        "facts": facts,
        "citations": citations,
    }


def resolve_item(source_id: str) -> str | None:
    """Map a stable source identifier (NCT, PMID) to the current sidecar id."""
    url = f"{API}/api/feed?q={urllib.parse.quote(source_id)}&limit=5"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.load(response)
    for item in data.get("items", []):
        if item["source_id"] == source_id:
            return item["item_id"]
    items = data.get("items") or []
    return items[0]["item_id"] if items else None


def check(case: dict, result: dict) -> list[str]:
    """Return a list of failure descriptions; empty means the case passed."""
    failures: list[str] = []
    answer = result["answer"] or ""
    lowered = answer.lower()

    expected_route = case.get("expect_route")
    if expected_route and result["route"] != expected_route:
        failures.append(f"route={result['route']!r} expected {expected_route!r}")

    allowed = case.get("expect_confidence")
    if allowed and result["confidence"] not in allowed:
        failures.append(f"confidence={result['confidence']!r} not in {allowed}")

    for number in case.get("expect_numbers", []):
        # Accept the bare figure or a thousands-separated rendering of it.
        variants = {str(number), f"{number:,}"}
        if not any(re.search(rf"\b{re.escape(v)}\b", answer) for v in variants):
            failures.append(f"missing number {number}")

    for needle in case.get("expect_contains", []):
        if needle.lower() not in lowered:
            failures.append(f"missing text {needle!r}")

    for needle in case.get("expect_absent", []):
        if needle.lower() in lowered:
            failures.append(f"contains forbidden text {needle!r}")

    wanted = case.get("must_retrieve_any_of")
    if wanted:
        retrieved = {e["source_id"] for e in result["evidence"]}
        if not (set(wanted) & retrieved):
            failures.append(f"retrieved none of {wanted}")

    if case.get("assert_citations_valid"):
        available = {e["item_id"] for e in result["evidence"]}
        bogus = [c for c in CITATION.findall(answer) if c not in available]
        if bogus:
            failures.append(f"cited records that were never retrieved: {bogus[:3]}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run a single question by id")
    parser.add_argument("--category", help="run one category")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    try:
        with urllib.request.urlopen(f"{API}/api/health", timeout=10) as response:
            health = json.load(response)
    except urllib.error.URLError as exc:
        print(f"API unreachable at {API}: {exc}")
        return 2
    if not health.get("llm_configured"):
        print("HF_TOKEN is not configured — every chat case would fail. Set it in phase2/.env")
        return 2

    cases = yaml.safe_load(GOLDEN.read_text())["questions"]
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if not cases:
        print("No matching questions.")
        return 2

    by_category: dict[str, list[bool]] = defaultdict(list)
    failed: list[tuple[str, list[str]]] = []

    print(f"Running {len(cases)} golden questions against {health['llm_model']}\n")

    for case in cases:
        label = f"{case['id']:<28}"
        try:
            if case.get("scope") == "item":
                item_id = resolve_item(case["item_source_id"])
                if not item_id:
                    raise RuntimeError(f"could not resolve {case['item_source_id']}")
                result = stream_chat(
                    f"/api/chat/item/{urllib.parse.quote(item_id)}",
                    {"message": case["question"]},
                )
            else:
                result = stream_chat(
                    "/api/chat/global",
                    {"message": case["question"], "thread_id": f"eval:{case['id']}"},
                )
        except Exception as exc:  # noqa: BLE001
            print(f"{label} ERROR  {type(exc).__name__}: {exc}")
            by_category[case["category"]].append(False)
            failed.append((case["id"], [f"exception: {exc}"]))
            continue

        problems = check(case, result)
        by_category[case["category"]].append(not problems)
        status = "PASS" if not problems else "FAIL"
        print(f"{label} {status}   [{result['confidence']}] route={result['route']}")
        if problems:
            failed.append((case["id"], problems))
            for problem in problems:
                print(f"{'':<28}   - {problem}")
        if args.verbose:
            print(f"{'':<28}   > {result['answer'][:300]}")

    print("\n" + "=" * 62)
    print(f"{'category':<26} {'pass':>5} {'total':>6}")
    print("-" * 62)
    total_pass = total = 0
    for category, results in sorted(by_category.items()):
        passed = sum(results)
        total_pass += passed
        total += len(results)
        print(f"{category:<26} {passed:>5} {len(results):>6}")
    print("-" * 62)
    print(f"{'TOTAL':<26} {total_pass:>5} {total:>6}")

    # Abstention recall is reported separately because it is the metric that
    # matters most: answering a question the corpus cannot support is the worst
    # failure this system has.
    abstention = by_category.get("insufficient_evidence", [])
    if abstention:
        recall = sum(abstention) / len(abstention)
        print(f"\nAbstention recall: {recall:.0%} ({sum(abstention)}/{len(abstention)})")
        if recall < 1.0:
            print("  Below 100% — the assistant answered something the corpus cannot support.")

    if failed:
        print(f"\n{len(failed)} question(s) failed.")
        return 1
    print("\nAll questions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
