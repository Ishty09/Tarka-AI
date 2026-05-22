"""Roast My X service (CLAUDE.md §9.2.2).

Single quarrel-argue call. Persists as a conversation (mode='roast_my_x')
with conversations.metadata.target=<slug> so the user can find each
landing-driven roast in their conversation list and continue if they want.

Counts as 1 message per §9.2.2 (standard quota).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from supabase import AsyncClient

from app.prompts.roast_my_x import (
    ROAST_MY_X_PROMPT,
    ROAST_TARGETS,
    TARGET_LABELS,
)
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


CONTENT_MAX_CHARS = 6000
HOST_PERSONA_SLUG = "devils_advocate"

MIN_ROAST_CHARS = 80
MAX_ROAST_CHARS = 1200


class UnknownTargetError(Exception):
    pass


@dataclass(slots=True)
class RoastMyXRun:
    target: str
    content: str
    roast: str
    conversation_id: str | None = None
    assistant_message_id: int | None = None


def is_known_target(target: str) -> bool:
    return target in ROAST_TARGETS


def target_label(target: str) -> str:
    return TARGET_LABELS.get(target, target.replace("-", " "))


async def generate_roast(
    *,
    target: str,
    content: str,
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> str | None:
    if not is_known_target(target):
        raise UnknownTargetError(target)

    llm = client or get_llm_client()
    body = (
        f"<target>{target_label(target)}</target>\n"
        f"<content>\n{content.strip()}\n</content>"
    )

    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": ROAST_MY_X_PROMPT},
                {"role": "user", "content": body},
            ],
            temperature=0.85,
            max_tokens=400,
            user=user_id,
            metadata=build_trace_metadata(
                name="roast_my_x",
                user_id=user_id,
                mode="roast_my_x",
                extra={"target": target},
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("roast_my_x.llm_error", target=target, user_id=user_id, error=str(err))
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

    text = raw.strip().strip('"').strip()
    if len(text) < MIN_ROAST_CHARS:
        log.warning("roast_my_x.too_short", target=target, length=len(text))
        return None
    if len(text) > MAX_ROAST_CHARS:
        text = text[:MAX_ROAST_CHARS].rstrip()
    return text


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
        raise RuntimeError("no_persona_rows_for_roast_my_x_host")
    return str(rows[0]["id"])


async def persist_roast_my_x_run(
    supabase: AsyncClient,
    *,
    user_id: str,
    run: RoastMyXRun,
) -> RoastMyXRun:
    conversation_id = str(uuid.uuid4())
    host = await _load_host_persona_id(supabase)
    label = target_label(run.target)

    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "persona_id": host,
                "mode": "roast_my_x",
                "title": f"Roast My {label.title()}",
                "metadata": {
                    "tool": "roast_my_x",
                    "target": run.target,
                    "target_label": label,
                },
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
                "content": run.content,
                "safety_verdict": "safe",
                "metadata": {"kind": "roast_my_x_content", "target": run.target},
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
                "content": run.roast,
                "safety_verdict": "safe",
                "model": QUARREL_ARGUE,
                "metadata": {"kind": "roast_my_x_roast", "target": run.target},
            }
        )
        .execute()
    )
    inserted = _rows(assistant_res.data)
    run.conversation_id = conversation_id
    run.assistant_message_id = int(inserted[0]["id"]) if inserted else None
    return run


async def run_roast_my_x(
    supabase: AsyncClient,
    *,
    user_id: str,
    target: str,
    content: str,
    client: LiteLLMClient | None = None,
) -> RoastMyXRun | None:
    roast = await generate_roast(
        target=target,
        content=content,
        client=client,
        user_id=user_id,
    )
    if roast is None:
        return None
    run = RoastMyXRun(target=target, content=content, roast=roast)
    return await persist_roast_my_x_run(supabase, user_id=user_id, run=run)


__all__ = [
    "CONTENT_MAX_CHARS",
    "MAX_ROAST_CHARS",
    "MIN_ROAST_CHARS",
    "ROAST_TARGETS",
    "RoastMyXRun",
    "UnknownTargetError",
    "generate_roast",
    "is_known_target",
    "persist_roast_my_x_run",
    "run_roast_my_x",
    "target_label",
]
