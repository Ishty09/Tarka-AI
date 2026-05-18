"""Past Self service (CLAUDE.md §9.1.5).

Single quarrel-argue call returning plain-text rebuttal. Persists as a
conversation (mode='past_self') with the past content as the user message
and the rebuttal as the assistant message — that way subsequent /chat/[id]
turns see the past content in history and the AI naturally keeps opposing.

Quota: counts as one message (§9.1.5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from supabase import AsyncClient

from app.prompts.past_self import PAST_SELF_PROMPT
from app.services._db_typing import row_or_none, rows as _rows
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)


PAST_CONTENT_MAX_CHARS = 4000
HOST_PERSONA_SLUG = "devils_advocate"

# Length guard — short replies are usually refusals or malformed
# continuations; drop and let the user retry.
MIN_REBUTTAL_CHARS = 150
MAX_REBUTTAL_CHARS = 3000


@dataclass(slots=True)
class PastSelfRun:
    past_content: str
    rebuttal: str
    conversation_id: str | None = None
    assistant_message_id: int | None = None


async def generate_rebuttal(
    past_content: str,
    *,
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> str | None:
    llm = client or get_llm_client()
    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": PAST_SELF_PROMPT},
                {"role": "user", "content": past_content},
            ],
            temperature=0.6,
            max_tokens=600,
            user=user_id,
            metadata={
                "generation_name": "past_self",
                "trace_user_id": user_id,
                "tags": ["past_self"],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("past_self.llm_error", user_id=user_id, error=str(err))
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
    if len(content) < MIN_REBUTTAL_CHARS:
        log.warning("past_self.too_short", user_id=user_id, length=len(content))
        return None
    if len(content) > MAX_REBUTTAL_CHARS:
        content = content[:MAX_REBUTTAL_CHARS]
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
        raise RuntimeError("no_persona_rows_for_past_self_host")
    return str(rows[0]["id"])


async def persist_past_self_run(
    supabase: AsyncClient,
    *,
    user_id: str,
    run: PastSelfRun,
) -> PastSelfRun:
    conversation_id = str(uuid.uuid4())
    host = await _load_host_persona_id(supabase)

    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "persona_id": host,
                "mode": "past_self",
                # Stash the raw past_content in metadata so a future
                # mode-aware chat assembly can re-inject it on every turn.
                "metadata": {"tool": "past_self", "past_content": run.past_content},
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
                "content": run.past_content,
                "safety_verdict": "safe",
                "metadata": {"kind": "past_self_quote"},
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
                "content": run.rebuttal,
                "safety_verdict": "safe",
                "model": QUARREL_ARGUE,
                "metadata": {"kind": "past_self_rebuttal"},
            }
        )
        .execute()
    )
    inserted = _rows(assistant_res.data)
    run.conversation_id = conversation_id
    run.assistant_message_id = int(inserted[0]["id"]) if inserted else None
    return run


async def run_past_self(
    supabase: AsyncClient,
    *,
    user_id: str,
    past_content: str,
    client: LiteLLMClient | None = None,
) -> PastSelfRun | None:
    rebuttal = await generate_rebuttal(past_content, client=client, user_id=user_id)
    if rebuttal is None:
        return None
    run = PastSelfRun(past_content=past_content, rebuttal=rebuttal)
    return await persist_past_self_run(supabase, user_id=user_id, run=run)


__all__ = [
    "MAX_REBUTTAL_CHARS",
    "MIN_REBUTTAL_CHARS",
    "PAST_CONTENT_MAX_CHARS",
    "PastSelfRun",
    "generate_rebuttal",
    "persist_past_self_run",
    "run_past_self",
]
