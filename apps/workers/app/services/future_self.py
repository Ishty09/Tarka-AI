"""Future Self service (CLAUDE.md §9.1.6).

Single quarrel-argue call returning plain-text message from the user's
80-year-old self. Persists as a conversation (mode='future_self') so the
user can keep arguing back inside it.

Quota: counts against messages_per_day (§9.1.6 — "standard quota").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from supabase import AsyncClient

from app.prompts.future_self import FUTURE_SELF_PROMPT
from app.services._db_typing import row_or_none, rows as _rows
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)


FUTURE_DECISION_MAX_CHARS = 4000
HOST_PERSONA_SLUG = "devils_advocate"

MIN_MESSAGE_CHARS = 150
MAX_MESSAGE_CHARS = 3000


@dataclass(slots=True)
class FutureSelfRun:
    decision: str
    message: str
    conversation_id: str | None = None
    assistant_message_id: int | None = None


async def generate_future_self_message(
    decision: str,
    *,
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> str | None:
    llm = client or get_llm_client()
    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": FUTURE_SELF_PROMPT},
                {"role": "user", "content": decision},
            ],
            temperature=0.7,
            max_tokens=600,
            user=user_id,
            metadata={
                "generation_name": "future_self",
                "trace_user_id": user_id,
                "tags": ["future_self"],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("future_self.llm_error", user_id=user_id, error=str(err))
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

    content = raw.strip()
    if len(content) < MIN_MESSAGE_CHARS:
        log.warning("future_self.too_short", user_id=user_id, length=len(content))
        return None
    if len(content) > MAX_MESSAGE_CHARS:
        content = content[:MAX_MESSAGE_CHARS]
    return content


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
        raise RuntimeError("no_persona_rows_for_future_self_host")
    return str(rows[0]["id"])


async def persist_future_self_run(
    supabase: AsyncClient,
    *,
    user_id: str,
    run: FutureSelfRun,
) -> FutureSelfRun:
    conversation_id = str(uuid.uuid4())
    host = await _load_host_persona_id(supabase)

    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "persona_id": host,
                "mode": "future_self",
                "metadata": {"tool": "future_self", "decision": run.decision},
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
                "metadata": {"kind": "future_self_decision"},
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
                "content": run.message,
                "safety_verdict": "safe",
                "model": QUARREL_ARGUE,
                "metadata": {"kind": "future_self_message"},
            }
        )
        .execute()
    )
    inserted = _rows(assistant_res.data)
    run.conversation_id = conversation_id
    run.assistant_message_id = int(inserted[0]["id"]) if inserted else None
    return run


async def run_future_self(
    supabase: AsyncClient,
    *,
    user_id: str,
    decision: str,
    client: LiteLLMClient | None = None,
) -> FutureSelfRun | None:
    message = await generate_future_self_message(decision, client=client, user_id=user_id)
    if message is None:
        return None
    run = FutureSelfRun(decision=decision, message=message)
    return await persist_future_self_run(supabase, user_id=user_id, run=run)


__all__ = [
    "FUTURE_DECISION_MAX_CHARS",
    "FutureSelfRun",
    "MAX_MESSAGE_CHARS",
    "MIN_MESSAGE_CHARS",
    "generate_future_self_message",
    "persist_future_self_run",
    "run_future_self",
]
