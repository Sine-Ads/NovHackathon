"""HuggingFace Inference wrapper.

Follows the ``InferenceClient.chat_completion`` pattern already proven in
``llm_1/llm_classifier.py``, on a larger model: the global assistant ships a
landscape block, a facts table and several excerpts in one prompt, and the
summary path depends on the model returning parseable JSON.

The JSON retry differs deliberately from llm_1's. Retrying an identical prompt
after a parse failure tends to reproduce the identical failure, so the second
attempt carries a repair instruction and the offending output.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator, Optional

from api.config import HF_TOKEN, LLM_MODEL

_client = None


class LLMUnavailable(RuntimeError):
    """Raised when the model cannot be reached or no token is configured."""


def get_client():
    global _client
    if _client is None:
        if not HF_TOKEN:
            raise LLMUnavailable(
                "HF_TOKEN is not set. Add it to phase2/.env — summaries and chat "
                "need it; browsing and search do not."
            )
        from huggingface_hub import InferenceClient

        _client = InferenceClient(token=HF_TOKEN)
    return _client


def complete(
    messages: list[dict[str, str]],
    max_tokens: int = 700,
    temperature: float = 0.2,
    model: Optional[str] = None,
) -> str:
    try:
        response = get_client().chat_completion(
            messages=messages,
            model=model or LLM_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""
    except LLMUnavailable:
        raise
    except Exception as exc:  # network, rate limit, model unavailable
        raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc


def stream(
    messages: list[dict[str, str]],
    max_tokens: int = 900,
    temperature: float = 0.3,
    model: Optional[str] = None,
) -> Iterator[str]:
    """Yield content deltas as they arrive."""
    try:
        for chunk in get_client().chat_completion(
            messages=messages,
            model=model or LLM_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        ):
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None)
            if piece:
                yield piece
    except LLMUnavailable:
        raise
    except Exception as exc:
        raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> Optional[dict[str, Any]]:
    """Parse a JSON object out of a model reply, tolerating fences and prose."""
    if not text:
        return None
    candidates = [text.strip()]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def complete_json(
    messages: list[dict[str, str]],
    max_tokens: int = 700,
    temperature: float = 0.1,
) -> Optional[dict[str, Any]]:
    """Ask for JSON, and repair once on a parse failure.

    The repair turn shows the model its own unparseable output rather than
    resending the original prompt unchanged.
    """
    raw = complete(messages, max_tokens=max_tokens, temperature=temperature)
    parsed = extract_json(raw)
    if parsed is not None:
        return parsed

    repair = messages + [
        {"role": "assistant", "content": raw[:1500]},
        {
            "role": "user",
            "content": (
                "That was not valid JSON. Reply with the JSON object only — no "
                "prose, no markdown fences, starting with { and ending with }."
            ),
        },
    ]
    return extract_json(complete(repair, max_tokens=max_tokens, temperature=0.0))
