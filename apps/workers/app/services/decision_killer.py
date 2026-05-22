"""Decision Killer service (CLAUDE.md §9.5.1).

Single quarrel-argue call, JSON-validated, persisted as a conversation
(mode='decision_killer') so the user can keep arguing inside it. Quota:
counts as one message (§9.5.1).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient

from app.prompts.decision_killer import DECISION_KILLER_PROMPT
from app.services._db_typing import row_or_none, rows as _rows
from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)


DECISION_MAX_CHARS = 4000
HOST_PERSONA_SLUG = "devils_advocate"


class WrongReason(BaseModel):
    reason: str = Field(min_length=1, max_length=200)
    argument: str = Field(min_length=1, max_length=600)


class DecisionKillerResult(BaseModel):
    reasons_wrong: list[WrongReason] = Field(min_length=3, max_length=3)
    one_reason_right: str = Field(min_length=10, max_length=1200)
    actual_avoidance: str = Field(min_length=5, max_length=400)


@dataclass(slots=True)
class DecisionKillerRun:
    decision: str
    result: DecisionKillerResult
    conversation_id: str | None = None
    assistant_message_id: int | None = None


async def generate_decision_killer(
    decision: str,
    *,
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> DecisionKillerResult | None:
    llm = client or get_llm_client()
    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": DECISION_KILLER_PROMPT},
                {"role": "user", "content": decision},
            ],
            temperature=0.5,
            response_format={"type": "json_object"},
            user=user_id,
            metadata=build_trace_metadata(
                name="decision_killer",
                user_id=user_id,
                mode="decision_killer",
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("decision_killer.llm_error", user_id=user_id, error=str(err))
        return None

    try:
        raw = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return None
    if isinstance(raw, list):
        raw = "".join(
            block.get("text", "")
            for block in raw
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if not isinstance(raw, str):
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("decision_killer.json_decode_failed", raw=raw[:200])
        return None
    try:
        return DecisionKillerResult.model_validate(parsed)
    except ValidationError as err:
        log.warning("decision_killer.schema_invalid", error=str(err))
        return None


async def _load_host_persona_id(supabase: AsyncClient) -> str:
    res = (
        await supabase.table("personas")
        .select("id")
        .eq("slug", HOST_PERSONA_SLUG)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row and row.get("id"):
        return str(row["id"])
    fallback = await supabase.table("personas").select("id").limit(1).execute()
    rows = _rows(fallback.data)
    if not rows:
        raise RuntimeError("no_persona_rows_for_decision_killer_host")
    return str(rows[0]["id"])


def _render_assistant_content(result: DecisionKillerResult) -> str:
    """Markdown rendering for the persisted assistant message body.

    The structured fields are also stored in metadata, but the bubble text
    needs human-readable content so /chat/[id] can show the result without
    bespoke rendering.
    """

    lines = ["## 3 Reasons This Is Wrong"]
    for i, r in enumerate(result.reasons_wrong, start=1):
        lines.append(f"{i}. **{r.reason}** — {r.argument}")
    lines.append("")
    lines.append("## 1 Reason It Might Be Right")
    lines.append(result.one_reason_right)
    lines.append("")
    lines.append("## What You're Actually Avoiding")
    lines.append(result.actual_avoidance)
    return "\n".join(lines)


async def persist_decision_killer_run(
    supabase: AsyncClient,
    *,
    user_id: str,
    run: DecisionKillerRun,
) -> DecisionKillerRun:
    conversation_id = str(uuid.uuid4())
    host = await _load_host_persona_id(supabase)

    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "persona_id": host,
                "mode": "decision_killer",
                "metadata": {"tool": "decision_killer"},
            }
        )
        .execute()
    )

    await (
        supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": "user",
                "content": run.decision,
                "safety_verdict": "safe",
            }
        )
        .execute()
    )

    assistant_res = (
        await supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "user_id": None,
                "role": "assistant",
                "content": _render_assistant_content(run.result),
                "safety_verdict": "safe",
                "model": QUARREL_ARGUE,
                "metadata": {
                    "kind": "decision_killer",
                    "reasons_wrong": [r.model_dump() for r in run.result.reasons_wrong],
                    "one_reason_right": run.result.one_reason_right,
                    "actual_avoidance": run.result.actual_avoidance,
                },
            }
        )
        .execute()
    )
    inserted = _rows(assistant_res.data)
    run.conversation_id = conversation_id
    run.assistant_message_id = int(inserted[0]["id"]) if inserted else None
    return run


async def run_decision_killer(
    supabase: AsyncClient,
    *,
    user_id: str,
    decision: str,
    client: LiteLLMClient | None = None,
) -> DecisionKillerRun | None:
    result = await generate_decision_killer(decision, client=client, user_id=user_id)
    if result is None:
        return None
    run = DecisionKillerRun(decision=decision, result=result)
    return await persist_decision_killer_run(supabase, user_id=user_id, run=run)


__all__ = [
    "DECISION_MAX_CHARS",
    "DecisionKillerResult",
    "DecisionKillerRun",
    "WrongReason",
    "generate_decision_killer",
    "persist_decision_killer_run",
    "run_decision_killer",
]
