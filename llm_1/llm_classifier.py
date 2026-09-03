import os
import json
from typing import Any, Dict, List, Optional

from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()
MODEL = os.environ.get("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
HF_TOKEN = (os.environ.get("HF_TOKEN") or "").strip() or None
PROVIDER = os.environ.get("HF_PROVIDER", "auto")
client = InferenceClient(provider=PROVIDER, token=HF_TOKEN)
VALID_CATEGORIES = {"proven_right", "proven_false", "proven_false_but_useful", "still_working_on"}
COUNCIL_MODELS = tuple(
    # Verify each model's Inference Providers listing before running. The first
    # model was confirmed by the project owner; the other defaults need checking.
    model.strip()
    for model in os.environ.get(
        "HF_COUNCIL_MODELS",
        "meta-llama/Llama-3.1-8B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-3B-Instruct",
    ).split(",")
    if model.strip()
)


def _build_prompt(paper: Dict[str, Any]) -> str:
    return f"""You are classifying medical research papers and news articles into 4 categories based on the criterias given to you
Categories:
- proven_right: results independently confirmed (meta-analysis, replication, or strong RCT with no contradicting evidence)
- proven_false: results contradicted, trial failed/terminated, or retracted
- proven_false_but_useful: failed/retracted, but the data has been cited or reused for other findings
- still_working_on: preprint, early-phase, or recruiting with no established results yet

Title: {paper['title']}
Abstract: {paper['abstract']}
Source: {paper['source']}
Publication type: {paper['publication_type']}
Trial status: {paper['trial_status']}
Retracted: {paper['retracted']}
Citation count: {paper['citation_count']}

Respond with ONLY valid JSON in this exact shape, nothing else:
{{"category": "<one of the four category names>", "justification": "<one sentence>"}}"""


def _parse_response(response: Any) -> Dict[str, str]:
    raw_reply = response.choices[0].message.content
    parsed = json.loads(raw_reply)
    category = parsed.get("category")
    justification = parsed.get("justification")
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category returned: {category}")
    if not isinstance(justification, str) or not justification.strip():
        raise ValueError("Missing justification in model response")
    return {"category": category, "justification": justification.strip()}


def _call_model(paper: Dict[str, Any], model: str) -> Dict[str, str]:
    prompt = _build_prompt(paper)
    request = {
        "messages": [{"role": "user", "content": prompt}],
        "model": model,
        "max_tokens": 200,
        "temperature": 0.1,
    }
    try:
        response = client.chat_completion(
            **request,
            response_format={"type": "json_object"},
        )
    except Exception:
        # Some providers reject response_format; the prompt still enforces JSON.
        response = client.chat_completion(**request)
    return _parse_response(response)


def classify_with_llm(paper, model: Optional[str] = None):
    """Classify one paper with one model, retrying once on failure."""
    if not HF_TOKEN:
        return {
            "category": None,
            "justification": None,
            "reason": "HF_TOKEN is not set in this terminal",
        }

    selected_model = model or MODEL
    last_reason = None

    for attempt in range(2):
        try:
            parsed = _call_model(paper, selected_model)

            return {
                "category": parsed["category"],
                "justification": parsed["justification"],
                "reason": None,
            }

        except (json.JSONDecodeError, ValueError) as e:
            last_reason = f"Invalid response: {e}"
            continue

        except Exception as e:
            last_reason = f"API call failed: {e}"
            continue

    return {"category": None, "justification": None, "reason": last_reason}


def classify_with_council(paper):
    """Classify with every council model and require a strict majority."""
    if not HF_TOKEN:
        return {"category": None, "justification": None, "reason": "HF_TOKEN is not set in this terminal"}

    responses: List[Dict[str, str]] = []
    failures: List[str] = []
    for model in COUNCIL_MODELS:
        result = classify_with_llm(paper, model=model)
        if result["category"] is None:
            failures.append(f"{model}: {result['reason']}")
        else:
            responses.append({
                "model_name": model,
                "category": result["category"],
                "justification": result["justification"],
            })

    if not responses:
        return {"category": None, "justification": None, "reason": "; ".join(failures)}

    counts = {category: 0 for category in VALID_CATEGORIES}
    for response in responses:
        counts[response["category"]] += 1
    majority_category = max(counts, key=counts.get)
    majority_count = counts[majority_category]
    if majority_count < 2 or majority_count <= len(responses) / 2:
        votes = ", ".join(
            f"{response['model_name']}={response['category']}" for response in responses
        )
        reason = f"No majority among successful council responses: {votes}"
        if failures:
            reason += f"; failures: {'; '.join(failures)}"
        return {"category": None, "justification": None, "reason": reason}

    agreeing = [response for response in responses if response["category"] == majority_category]
    justification = " ".join(response["justification"] for response in agreeing)
    return {"category": majority_category, "justification": justification, "reason": None}


