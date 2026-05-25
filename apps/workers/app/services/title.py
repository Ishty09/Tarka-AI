"""Conversation title generation.

Fire-and-forget background task. Called after the first assistant turn
of a brand-new conversation. Asks `quarrel-cheap` for a short 3-5 word
title based on the user's opening message, then updates the
conversation row.

If anything fails (LLM error, DB error), we log and move on — the
sidebar fallback in apps/web already uses the first user message as
the visible label, so a missing title is purely cosmetic.
"""

from __future__ import annotations

import structlog
from supabase import AsyncClient

from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services.llm import LiteLLMError, LiteLLMNetworkError, QUARREL_CHEAP, get_llm_client

log = structlog.get_logger(__name__)


TITLE_SYSTEM_PROMPT = (
    "Generate a 3-6 word title summarizing this conversation. "
    "No quotes, no trailing period, no emoji. "
    "Examples: 'Quitting job for YouTube', 'Pricing dispute with cofounder', "
    "'Roast of resume opening line'. Reply with the title only."
)


async def maybe_generate_title(
    supabase: AsyncClient,
    *,
    conversation_id: str,
    user_id: str,
    user_message: str,
) -> None:
    """Generate + persist a title. Safe to call without awaiting."""

    if not user_message.strip():
        return

    client = get_llm_client()
    try:
        result = await client.chat(
            model=QUARREL_CHEAP,
            messages=[
                {"role": "system", "content": TITLE_SYSTEM_PROMPT},
                {"role": "user", "content": user_message[:1000]},
            ],
            max_tokens=20,
            metadata=build_trace_metadata(
                name="title_gen",
                user_id=user_id,
                session_id=conversation_id,
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("title_gen.llm_error", conversation_id=conversation_id, error=str(err))
        return

    try:
        title = (
            result["choices"][0]["message"]["content"]
            .strip()
            .strip('"\'')
            .rstrip(".")
        )[:120]
    except (KeyError, IndexError, AttributeError):
        return

    if not title:
        return

    try:
        await (
            supabase.table("conversations")
            .update({"title": title})
            .eq("id", conversation_id)
            .is_("title", None)  # don't clobber if something already set it
            .execute()
        )
    except Exception as err:  # noqa: BLE001 — best-effort
        log.warning(
            "title_gen.persist_failed",
            conversation_id=conversation_id,
            error=str(err),
        )
