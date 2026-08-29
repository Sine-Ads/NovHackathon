import os
from huggingface_hub import InferenceClient
import json
from dotenv import load_dotenv

load_dotenv()
MODEL = "meta-llama/Llama-3.1-8B-Instruct"
HF_TOKEN = os.environ.get("HF_TOKEN")
client = InferenceClient(token=HF_TOKEN)
VALID_CATEGORIES = {"proven_right", "proven_false", "proven_false_but_useful", "still_working_on"}

def classify_with_llm(paper):
    prompt = f"""You are classifying medical research papers and news articles into 4 categories based on the criterias given to you
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

    last_reason = None

    for attempt in range(2):
        try:
            response = client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL,
                max_tokens=200,
                temperature=0.1,
            )
            raw_reply = response.choices[0].message.content
            parsed = json.loads(raw_reply)

            if parsed["category"] not in VALID_CATEGORIES:
                raise ValueError(f"Invalid category returned: {parsed['category']}")

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


