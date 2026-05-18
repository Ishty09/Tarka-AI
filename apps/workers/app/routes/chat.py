"""POST /chat/stream — Server-Sent Events streaming chat turn.

The single hottest path in the app. Per CLAUDE.md §8.3 every request flows:

    apps/web /api/chat/stream  →  this handler  →  LiteLLM proxy

In order:

  1. Auth (WORKERS_INTERNAL_SECRET + X-User-Id header) — apps/web is the
     trust boundary; this endpoint is never on the public internet.
  2. Idempotency replay check (§1.11, §6.5).
  3. Resolve persona + conversation (create the conversation on first turn).
  4. Quota check (§8.3 step 3 — 429 with upgrade_url payload).
  5. Safety screen (§1.5). Non-safe verdicts short-circuit with a one-shot
     SSE event and persist a safety_incidents row downstream (TODO Phase H).
  6. Persist the user message (redacted variant for non-safe).
  7. Assemble system + history + user, stream from LiteLLM, relay SSE.
  8. Persist the assistant message + increment quota.

Fact extraction (§7.2 row) is queued for Phase C and is left as a TODO.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import AsyncClient

from app.config import get_settings
from app.prompts.anti_sycophant_base import ANTI_SYCOPHANT_BASE_PROMPT
from app.services import fact_extraction
from app.services._db_typing import row_or_none, rows as _rows
from app.services.idempotency import check_idempotency, record_idempotency
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)
from app.services.memory import (
    ContradictionCallout,
    find_relevant_contradiction,
    load_user_facts,
    mark_contradiction_surfaced,
)
from app.services.quotas import get_message_quota, increment_message_count
from app.services.safety import classify_message, redact
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

ConversationMode = Literal[
    "argue",
    "roast",
    "mediate",
    "council",
    "negotiate",
    "custom",
    "roast_my_x",
    "decision_killer",
    "cope_detector",
    "steelman",
    "future_self",
    "past_self",
    "drill_sergeant",
]


# ----- Auth dependency -------------------------------------------------------


def _verify_internal_caller(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """apps/web forwards every chat call with the shared secret (§22)."""

    settings = get_settings()
    if not settings.workers_internal_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "internal_secret_unset")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.workers_internal_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token")


def _require_user(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> str:
    if not x_user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_user")
    return x_user_id


# ----- Wire shape (mirrors packages/shared chatStreamRequestSchema) ---------


class ChatStreamRequest(BaseModel):
    conversation_id: str | None = None
    persona_slug: str | None = None
    mode: ConversationMode
    message: str = Field(min_length=1, max_length=8000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    couple_link_id: str | None = None
    group_room_id: str | None = None


# ----- Route -----------------------------------------------------------------


@router.post(
    "/stream",
    dependencies=[Depends(_verify_internal_caller)],
)
async def chat_stream(
    req: ChatStreamRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> StreamingResponse:
    supabase = await get_supabase()
    llm = get_llm_client()

    # ----- Idempotency replay -------------------------------------------------
    payload_hash = _hash_payload(req)
    replay = await check_idempotency(
        supabase,
        key=req.idempotency_key,
        scope="chat.stream",
        user_id=user_id,
    )
    if replay is not None and replay.get("response_body") is not None:
        body = replay["response_body"]
        return _replay_stream(body)

    # ----- Persona + conversation --------------------------------------------
    conversation = await _resolve_conversation(
        supabase,
        user_id=user_id,
        conversation_id=req.conversation_id,
        persona_slug=req.persona_slug,
        mode=req.mode,
        couple_link_id=req.couple_link_id,
        group_room_id=req.group_room_id,
    )

    # ----- Quota check --------------------------------------------------------
    quota = await get_message_quota(supabase, user_id)
    if quota.exceeded:
        return _quota_exceeded_response(quota)

    # ----- Safety screen ------------------------------------------------------
    verdict = await classify_message(
        req.message,
        user_id=user_id,
        conversation_id=conversation["id"],
        client=llm,
    )
    redacted_message = redact(req.message, verdict.redactions)

    # Reserve the idempotency row before any side-effects.
    await record_idempotency(
        supabase,
        key=req.idempotency_key,
        scope="chat.stream",
        user_id=user_id,
        payload_hash=payload_hash,
        response_body=None,
    )

    if verdict.verdict != "safe":
        # Short-circuit: persist the user message stamped with the verdict and
        # emit a single refusal event. Crisis handling (hotlines, emergency
        # contact ping) lands in Phase H.
        await _persist_user_message(
            supabase,
            conversation_id=conversation["id"],
            user_id=user_id,
            content=req.message,
            redacted_content=redacted_message,
            safety_verdict=verdict.verdict,
        )
        return StreamingResponse(
            _refusal_stream(verdict.verdict, verdict.reason),
            media_type="text/event-stream",
        )

    # ----- Persist user message ----------------------------------------------
    user_message_id = await _persist_user_message(
        supabase,
        conversation_id=conversation["id"],
        user_id=user_id,
        content=req.message,
        redacted_content=None,
        safety_verdict="safe",
    )

    # ----- Assemble messages + stream ----------------------------------------
    system_blocks, fact_ids = await _build_system_blocks(
        supabase,
        user_id=user_id,
        persona_system_prompt=conversation["persona_system_prompt"],
        query_message=req.message,
    )
    # §9.4.4 inline callout: surface at most one unsurfaced contradiction
    # whose facts overlap with the retrieved memory bundle.
    callout = await find_relevant_contradiction(
        supabase,
        user_id,
        fact_ids=fact_ids,
    )
    history = await _load_history(supabase, conversation_id=conversation["id"], limit=20)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_blocks}, *history]

    return StreamingResponse(
        _stream_assistant(
            llm=llm,
            supabase=supabase,
            messages=messages,
            user_id=user_id,
            conversation_id=conversation["id"],
            idempotency_key=req.idempotency_key,
            payload_hash=payload_hash,
            user_message=req.message,
            user_message_id=user_message_id,
            callout=callout,
        ),
        media_type="text/event-stream",
    )


# ----- Streaming generator ---------------------------------------------------


async def _stream_assistant(
    *,
    llm: LiteLLMClient,
    supabase: AsyncClient,
    messages: list[dict[str, Any]],
    user_id: str,
    conversation_id: str,
    idempotency_key: str,
    payload_hash: str,
    user_message: str,
    user_message_id: int,
    callout: ContradictionCallout | None = None,
) -> AsyncIterator[bytes]:
    started_at = time.perf_counter()
    accumulated: list[str] = []
    finish_reason: str | None = None
    cached_tokens: int | None = None

    # §9.4.4: emit any active contradiction callout BEFORE the model deltas
    # so the UI can pin a banner above the streaming reply. surfaced_at
    # stamp prevents repeat surfacing on subsequent turns.
    if callout is not None:
        yield _sse_event(
            "contradiction",
            {
                "id": callout.id,
                "severity": callout.severity,
                "summary": callout.summary,
                "fact_a": {
                    "text": callout.fact_a_text,
                    "created_at": callout.fact_a_created_at,
                },
                "fact_b": {
                    "text": callout.fact_b_text,
                    "created_at": callout.fact_b_created_at,
                },
            },
        )
        await mark_contradiction_surfaced(supabase, callout.id)

    try:
        async for chunk in llm.chat_stream(
            model=QUARREL_ARGUE,
            messages=messages,
            user=user_id,
            metadata={
                "generation_name": "chat.stream",
                "trace_user_id": user_id,
                "session_id": conversation_id,
                "tags": ["chat.stream"],
            },
        ):
            if chunk.delta:
                accumulated.append(chunk.delta)
                yield _sse_event("delta", {"text": chunk.delta})
            if chunk.finish_reason is not None:
                finish_reason = chunk.finish_reason
            if chunk.cached_tokens is not None:
                cached_tokens = chunk.cached_tokens
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("chat.stream.llm_error", error=str(err))
        yield _sse_event("error", {"reason": "llm_error"})
        return

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    full_text = "".join(accumulated)

    assistant_msg_id = await _persist_assistant_message(
        supabase,
        conversation_id=conversation_id,
        content=full_text,
        latency_ms=latency_ms,
        cached_input_tokens=cached_tokens,
    )

    await increment_message_count(supabase, user_id)

    await record_idempotency(
        supabase,
        key=idempotency_key,
        scope="chat.stream",
        user_id=user_id,
        payload_hash=payload_hash,
        response_body={"assistant_message_id": assistant_msg_id, "text": full_text},
        response_status=200,
    )

    yield _sse_event(
        "done",
        {
            "finish_reason": finish_reason,
            "assistant_message_id": assistant_msg_id,
            "latency_ms": latency_ms,
        },
    )

    # Fire-and-forget fact extraction (§7.2 row, §6.2 user_facts). Best-effort:
    # the service swallows its own errors so a bad LLM round-trip can't reach
    # the user. We don't await — the task runs after the response closes.
    _schedule_fact_extraction(
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=user_message,
        source_message_id=user_message_id,
    )


def _schedule_fact_extraction(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    source_message_id: int,
) -> None:
    """Spawn the extraction coroutine. Module-level so tests can monkeypatch."""

    asyncio.create_task(
        fact_extraction.extract_and_persist(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            source_message_id=source_message_id,
        )
    )


# ----- Helpers ---------------------------------------------------------------


async def _resolve_conversation(
    supabase: AsyncClient,
    *,
    user_id: str,
    conversation_id: str | None,
    persona_slug: str | None,
    mode: ConversationMode,
    couple_link_id: str | None,
    group_room_id: str | None,
) -> dict[str, Any]:
    """Return a dict with id + persona_system_prompt. Creates row on first turn."""

    if conversation_id is not None:
        existing = (
            await supabase.table("conversations")
            .select("id, user_id, persona_id, mode, metadata, couple_link_id")
            .eq("id", conversation_id)
            .maybe_single()
            .execute()
        )
        row = row_or_none(existing.data) if existing is not None else None
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation_not_found")

        # Ownership check. For couple-link conversations (§9.3.1) either
        # partner is allowed to post — both share the same conversation row.
        if row.get("user_id") != user_id:
            link_id = row.get("couple_link_id")
            allowed = False
            if link_id:
                link_res = (
                    await supabase.table("couple_links")
                    .select("user_a, user_b, status")
                    .eq("id", link_id)
                    .maybe_single()
                    .execute()
                )
                link_row = row_or_none(link_res.data) if link_res is not None else None
                if (
                    link_row is not None
                    and link_row.get("status") == "active"
                    and user_id in (link_row.get("user_a"), link_row.get("user_b"))
                ):
                    allowed = True
            if not allowed:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "not_conversation_owner")

        persona = await _load_persona_by_id(supabase, str(row["persona_id"]))
        # Negotiation Sparring (§9.5.3) and any future scenario-driven mode
        # writes a `system_prompt_override` into metadata. When present, we
        # use it INSTEAD of the persona's system_prompt so the roleplayed
        # counterparty stays in character across turns.
        metadata = row.get("metadata") or {}
        override = None
        if isinstance(metadata, dict):
            candidate = metadata.get("system_prompt_override")
            if isinstance(candidate, str) and candidate.strip():
                override = candidate
        system_prompt = override or persona["system_prompt"]
        return {
            "id": str(row["id"]),
            "persona_system_prompt": system_prompt,
            "system_prompt_overridden": override is not None,
        }

    if persona_slug is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "persona_required_for_new_conversation")

    persona = await _load_persona_by_slug(supabase, persona_slug)
    new_id = str(uuid.uuid4())
    insert_payload = {
        "id": new_id,
        "user_id": user_id,
        "persona_id": persona["id"],
        "mode": mode,
        "couple_link_id": couple_link_id,
        "group_room_id": group_room_id,
    }
    await supabase.table("conversations").insert(insert_payload).execute()
    return {"id": new_id, "persona_system_prompt": persona["system_prompt"]}


async def _load_persona_by_id(supabase: AsyncClient, persona_id: str) -> dict[str, Any]:
    res = (
        await supabase.table("personas")
        .select("id, system_prompt")
        .eq("id", persona_id)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "persona_not_found")
    return row


async def _load_persona_by_slug(supabase: AsyncClient, slug: str) -> dict[str, Any]:
    res = (
        await supabase.table("personas")
        .select("id, system_prompt")
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "persona_not_found")
    return row


async def _build_system_blocks(
    supabase: AsyncClient,
    *,
    user_id: str,
    persona_system_prompt: str,
    query_message: str,
) -> tuple[list[dict[str, Any]], list[int]]:
    """Assemble the system message as cache-controlled content blocks.

    §7.6 caching strategy splits the prompt into two segments:
      1. Anti-sycophant base + persona overlay — long-lived. Identical
         across turns of the same conversation, so OpenAI prompt caching
         auto-hits and Anthropic respects the cache_control marker.
      2. <user_facts> block — rotates per turn but still worth marking so
         repeat turns within a short window benefit.

    Both blocks use `cache_control: ephemeral` because Anthropic's 1-hour
    cache is beta and not in our locked stack — when it lands we can flip
    the static block to "persistent" without touching call sites.

    Mirrors packages/ai/src/caching.ts buildSystemMessage().
    """

    facts = await load_user_facts(supabase, user_id, query_message=query_message)
    log.info(
        "chat.system_prompt.facts",
        user_id=user_id,
        fact_count=facts.count,
    )

    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"{ANTI_SYCOPHANT_BASE_PROMPT}\n\n{persona_system_prompt}",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if facts.text:
        blocks.append(
            {
                "type": "text",
                "text": f"<user_facts>\n{facts.text}\n</user_facts>",
                "cache_control": {"type": "ephemeral"},
            }
        )
    return blocks, facts.fact_ids


async def _load_history(
    supabase: AsyncClient, *, conversation_id: str, limit: int
) -> list[dict[str, Any]]:
    res = (
        await supabase.table("messages")
        .select("role, content")
        .eq("conversation_id", conversation_id)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    raw_rows = _rows(res.data)
    history_rows = list(reversed(raw_rows))
    return [
        {"role": r["role"], "content": r["content"]}
        for r in history_rows
        if r["role"] in {"user", "assistant"}
    ]


async def _persist_user_message(
    supabase: AsyncClient,
    *,
    conversation_id: str,
    user_id: str,
    content: str,
    redacted_content: str | None,
    safety_verdict: str,
) -> int:
    res = (
        await supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": "user",
                "content": content,
                "redacted_content": redacted_content,
                "safety_verdict": safety_verdict,
            }
        )
        .execute()
    )
    inserted = _rows(res.data)
    return int(inserted[0]["id"]) if inserted else 0


async def _persist_assistant_message(
    supabase: AsyncClient,
    *,
    conversation_id: str,
    content: str,
    latency_ms: int,
    cached_input_tokens: int | None,
) -> int:
    res = (
        await supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "user_id": None,
                "role": "assistant",
                "content": content,
                "safety_verdict": "safe",
                "latency_ms": latency_ms,
                "cached_input_tokens": cached_input_tokens,
                "model": QUARREL_ARGUE,
            }
        )
        .execute()
    )
    inserted = _rows(res.data)
    return int(inserted[0]["id"]) if inserted else 0


def _hash_payload(req: ChatStreamRequest) -> str:
    payload = json.dumps(req.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sse_event(name: str, data: dict[str, Any]) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()


async def _refusal_stream(verdict: str, reason: str) -> AsyncIterator[bytes]:
    yield _sse_event("safety", {"verdict": verdict, "reason": reason})
    yield _sse_event("done", {"finish_reason": "safety_refusal"})


def _replay_stream(body: dict[str, Any]) -> StreamingResponse:
    text = body.get("text", "")
    assistant_id = body.get("assistant_message_id")

    async def generator() -> AsyncIterator[bytes]:
        if text:
            yield _sse_event("delta", {"text": text})
        yield _sse_event(
            "done",
            {"finish_reason": "replay", "assistant_message_id": assistant_id},
        )

    return StreamingResponse(generator(), media_type="text/event-stream")


def _quota_exceeded_response(quota: Any) -> StreamingResponse:
    payload = {
        "error": "quota_exceeded",
        "tier": quota.tier,
        "limit": quota.limit,
        "used": quota.used,
        "reset_at": quota.reset_at.isoformat(),
        "upgrade_url": "/pricing",
    }

    async def generator() -> AsyncIterator[bytes]:
        yield _sse_event("quota_exceeded", payload)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        status_code=429,
    )
