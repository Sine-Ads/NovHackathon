"""Chat orchestration for both assistants.

Scope and memory boundary, enforced here rather than merely described in a
prompt:

    item scope    evidence = the item + its nearest neighbours, nothing else
                  history  = that item's thread only
    global scope  evidence = landscape + facts + hybrid retrieval
                  history  = the global thread only

Three properties hold in both scopes:

  1. Threads never merge. An item thread cannot seed the global thread.
  2. Retrieval reruns from scratch on every turn. A fact seen in turn 2 is not
     available in turn 5 unless turn 5 retrieves it again.
  3. Only ``role`` and ``content`` are replayed. Prior evidence blocks are never
     resent, so stale context cannot masquerade as current retrieval.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Iterator, Optional

from api import aggregates, classifications, confidence, llm, prompts, retrieval, store
from api.config import MAX_HISTORY_TURNS
from api.evidence import Evidence
from api.landscape import to_prompt_block
from api.router import Route, route, suggest_aggregate

logger = logging.getLogger(__name__)


def _history_messages(side: sqlite3.Connection, thread_id: str) -> list[dict[str, str]]:
    """Recent turns, for continuity only. Evidence is deliberately excluded."""
    turns = store.get_history(side, thread_id, limit=MAX_HISTORY_TURNS * 2)
    return [{"role": t["role"], "content": t["content"]} for t in turns]


def _emit(event: str, payload: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event, **payload})}\n\n"


def _attach_verdicts(
    src: sqlite3.Connection, evidence: list[Evidence]
) -> list[Evidence]:
    """Look up classifier verdicts for retrieved records.

    Read at query time rather than from the index: the classifier runs on its
    own schedule, and a verdict copied into the sidecar would go stale without
    the content hash ever noticing.
    """
    verdicts = classifications.for_items(src, [e.item_id for e in evidence])
    for ev in evidence:
        ev.classification = verdicts.get(ev.item_id)
    return evidence


# ---------------------------------------------------------------------------
# Per-item chat
# ---------------------------------------------------------------------------


def item_chat(
    src: sqlite3.Connection,
    side: sqlite3.Connection,
    index,
    item_id: str,
    message: str,
) -> Iterator[str]:
    thread_id = f"item:{item_id}"
    store.ensure_thread(side, thread_id, "item", item_id)

    row = side.execute(
        """SELECT c.chunk_id, c.text, i.item_id, i.source_name, i.source_id,
                  i.source_url, i.title, i.date_published, i.date_class,
                  i.n_chars, i.is_thin
           FROM item i JOIN chunk c ON c.item_id = i.item_id
           WHERE i.item_id = ? ORDER BY c.chunk_index LIMIT 1""",
        (item_id,),
    ).fetchone()
    if row is None:
        logger.warning("Chat requested for unknown item %s", item_id)
        yield _emit("error", {"message": "That record could not be opened."})
        return

    primary = retrieval._to_evidence(row)
    primary.matched_by = ["primary"]
    primary.reason = "the record you opened"
    neighbours = retrieval.similar_items(side, index, item_id, k=5)
    evidence = _attach_verdicts(src, [primary] + neighbours)
    neighbours = evidence[1:]

    yield _emit(
        "evidence",
        {
            "scope": "item",
            "route": Route.RETRIEVAL.value,
            "evidence": [e.to_dict() for e in evidence],
        },
    )

    store.add_message(side, thread_id, "user", message)

    forced = confidence.gate(neighbours + [primary], Route.RETRIEVAL)
    if forced == confidence.INSUFFICIENT:
        text = confidence.insufficient_message(message, evidence, "item")
        yield _emit("delta", {"text": text})
        store.add_message(side, thread_id, "assistant", text, forced, [])
        yield _emit("done", {"confidence": forced, "citations": []})
        return

    messages = (
        [{"role": "system", "content": prompts.item_chat_system(primary, neighbours)}]
        + _history_messages(side, thread_id)
        + [{"role": "user", "content": message}]
    )

    yield from _stream_answer(side, thread_id, messages, evidence, Route.RETRIEVAL)


# ---------------------------------------------------------------------------
# Global chat
# ---------------------------------------------------------------------------


def global_chat(
    src: sqlite3.Connection,
    side: sqlite3.Connection,
    index,
    message: str,
    thread_id: str = "global",
) -> Iterator[str]:
    store.ensure_thread(side, thread_id, "global", None)

    chosen = route(message)
    stats = store.get_landscape(side) or {}
    landscape_block = to_prompt_block(stats) if stats else "(statistics unavailable)"

    evidence: list[Evidence] = []
    if chosen in (Route.RETRIEVAL, Route.BOTH):
        evidence = _attach_verdicts(
            src, retrieval.hybrid_search(side, index, message, k=8)
        )

    facts_block: Optional[str] = None
    if chosen in (Route.AGGREGATE, Route.BOTH):
        suggestion = suggest_aggregate(message)
        if suggestion:
            result = aggregates.run(src, suggestion["name"], suggestion["args"])
            facts_block = aggregates.to_facts_block(result)

    yield _emit(
        "evidence",
        {
            "scope": "global",
            "route": chosen.value,
            "evidence": [e.to_dict() for e in evidence],
            "facts": facts_block,
        },
    )

    store.add_message(side, thread_id, "user", message)

    forced = confidence.gate(evidence, chosen)
    if forced == confidence.INSUFFICIENT and not facts_block:
        text = confidence.insufficient_message(message, evidence, "global")
        yield _emit("delta", {"text": text})
        store.add_message(side, thread_id, "assistant", text, forced, [])
        yield _emit("done", {"confidence": forced, "citations": []})
        return

    system = prompts.global_chat_system(landscape_block, facts_block, evidence)
    if chosen in (Route.AGGREGATE, Route.BOTH) and not facts_block:
        system += "\n\n" + prompts.TOOL_INSTRUCTION

    messages = (
        [{"role": "system", "content": system}]
        + _history_messages(side, thread_id)
        + [{"role": "user", "content": message}]
    )

    yield from _stream_answer(
        side, thread_id, messages, evidence, chosen, src=src, allow_tool=facts_block is None
    )


# ---------------------------------------------------------------------------
# Shared streaming
# ---------------------------------------------------------------------------


def _stream_answer(
    side: sqlite3.Connection,
    thread_id: str,
    messages: list[dict[str, str]],
    evidence: list[Evidence],
    chosen: Route,
    src: Optional[sqlite3.Connection] = None,
    allow_tool: bool = False,
) -> Iterator[str]:
    """Stream a reply, resolving at most one tool call along the way."""
    buffer: list[str] = []
    # A tool call arrives as a bare JSON object, so while one is still possible
    # the stream is held back rather than shown to the user. As soon as the text
    # proves to be prose, everything withheld is flushed at once.
    withholding = allow_tool
    try:
        for piece in llm.stream(messages):
            buffer.append(piece)
            if withholding:
                joined = "".join(buffer).lstrip()
                still_possible = joined.startswith("{") and len(joined) < 400
                if still_possible:
                    continue
                withholding = False
                yield _emit("delta", {"text": "".join(buffer)})
                continue
            yield _emit("delta", {"text": piece})
    except llm.LLMUnavailable as exc:
        logger.warning("LLM unavailable mid-stream: %s", exc)
        text = (
            "The language model is unavailable right now, so I can't answer. "
            "The retrieved sources are listed below and remain usable."
        )
        yield _emit("delta", {"text": text})
        store.add_message(side, thread_id, "assistant", text, confidence.INSUFFICIENT, [])
        yield _emit("done", {"confidence": confidence.INSUFFICIENT, "citations": []})
        return

    raw = "".join(buffer)

    # One tool round-trip, never more: a second would risk a loop that burns
    # latency and the HF rate limit mid-demo.
    handled_tool = False
    if allow_tool and src is not None:
        parsed = llm.extract_json(raw)
        call = (parsed or {}).get("tool_call") if isinstance(parsed, dict) else None
        if call and call.get("name"):
            handled_tool = True
            result = aggregates.run(src, call["name"], call.get("args") or {})
            facts = aggregates.to_facts_block(result)
            yield _emit("facts", {"facts": facts, "query": call["name"]})
            follow_up = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"FACTS (exact database result):\n{facts}\n\n"
                        "Now answer the original question using these numbers. "
                        "Do not request another query."
                    ),
                },
            ]
            buffer = []
            try:
                for piece in llm.stream(follow_up):
                    buffer.append(piece)
                    yield _emit("delta", {"text": piece})
            except llm.LLMUnavailable as exc:
                logger.warning("LLM unavailable during tool follow-up: %s", exc)
                yield _emit(
                    "delta",
                    {"text": "\n(The model became unavailable before it could "
                             "use those numbers.)"},
                )
            raw = "".join(buffer)

    if withholding and not handled_tool:
        # Short reply that merely looked like a tool call. Release it.
        yield _emit("delta", {"text": raw})

    answer, claimed = confidence.parse_and_strip(raw)
    answer = confidence.strip_bad_citations(answer, evidence)
    level, citations = confidence.validate(answer, claimed, evidence, chosen)

    store.add_message(
        side,
        thread_id,
        "assistant",
        answer,
        level,
        [e.to_dict() for e in evidence[:8]],
    )
    yield _emit("done", {"confidence": level, "citations": citations})
