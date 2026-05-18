"""Steelman generator service (CLAUDE.md §9.1.3).

Single quarrel-argue call, JSON output validated against pydantic, persist
as a conversation (mode='steelman') so the user can revisit the result.
Quota-wise it counts as one message — the route increments
messages_used after a successful run.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Annotated, Any

import structlog
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient

from app.prompts.steelman import STEELMAN_PROMPT
from app.services._db_typing import row_or_none, rows as _rows
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)


POSITION_MAX_CHARS = 4000
# Persona slug we host the conversation under — devils_advocate is the
# canonical "argue" persona and pairs naturally with the steelman/devil's
# pairing in the §10.1 library.
HOST_PERSONA_SLUG = "devils_advocate"


class SteelmanCounter(BaseModel):
    counter: str = Field(min_length=1, max_length=400)
    response: str = Field(min_length=1, max_length=600)


class SteelmanResult(BaseModel):
    strongest_version: str = Field(min_length=20, max_length=4000)
    assumptions: list[str] = Field(min_length=1, max_length=5)
    evidence: list[str] = Field(min_length=1, max_length=5)
    counters: list[SteelmanCounter] = Field(min_length=1, max_length=5)


@dataclass(slots=True)
class SteelmanRun:
    position: str
    result: SteelmanResult
    conversation_id: str | None = None
    assistant_message_id: int | None = None


# ----- LLM call --------------------------------------------------------------


async def generate_steelman(
    position: str,
    *,
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> SteelmanResult | None:
    """Single LLM call. None on any defensive path."""

    llm = client or get_llm_client()
    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": STEELMAN_PROMPT},
                {"role": "user", "content": position},
            ],
            temperature=0.5,
            response_format={"type": "json_object"},
            user=user_id,
            metadata={
                "generation_name": "steelman",
                "trace_user_id": user_id,
                "tags": ["steelman"],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("steelman.llm_error", user_id=user_id, error=str(err))
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
        log.warning("steelman.json_decode_failed", raw=raw[:200])
        return None
    try:
        return SteelmanResult.model_validate(parsed)
    except ValidationError as err:
        log.warning("steelman.schema_invalid", error=str(err))
        return None


# ----- Persist + run --------------------------------------------------------


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
        raise RuntimeError("no_persona_rows_for_steelman_host")
    return str(rows[0]["id"])


async def persist_steelman_run(
    supabase: AsyncClient,
    *,
    user_id: str,
    run: SteelmanRun,
) -> SteelmanRun:
    conversation_id = str(uuid.uuid4())
    host = await _load_host_persona_id(supabase)

    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "persona_id": host,
                "mode": "steelman",
                "metadata": {"tool": "steelman"},
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
                "content": run.position,
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
                "content": run.result.strongest_version,
                "safety_verdict": "safe",
                "model": QUARREL_ARGUE,
                "metadata": {
                    "kind": "steelman",
                    "assumptions": run.result.assumptions,
                    "evidence": run.result.evidence,
                    "counters": [c.model_dump() for c in run.result.counters],
                },
            }
        )
        .execute()
    )
    inserted = _rows(assistant_res.data)
    run.conversation_id = conversation_id
    run.assistant_message_id = int(inserted[0]["id"]) if inserted else None
    return run


async def run_steelman(
    supabase: AsyncClient,
    *,
    user_id: str,
    position: str,
    client: LiteLLMClient | None = None,
) -> SteelmanRun | None:
    """End-to-end. None if the LLM call failed past the defensive paths."""

    result = await generate_steelman(position, client=client, user_id=user_id)
    if result is None:
        return None
    run = SteelmanRun(position=position, result=result)
    return await persist_steelman_run(supabase, user_id=user_id, run=run)


__all__ = [
    "POSITION_MAX_CHARS",
    "SteelmanCounter",
    "SteelmanResult",
    "SteelmanRun",
    "generate_steelman",
    "persist_steelman_run",
    "run_steelman",
]
