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
from app.services import analytics, fact_extraction
from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services._db_typing import row_or_none
from app.services._db_typing import rows as _rows
from app.services.enforcement import (
    SuspendedUserError,
    assert_not_suspended,
    check_quota,
    quota_detail,
)
from app.services.groups import (
    AI_TURN_TAKING_THRESHOLD,
    count_recent_consecutive_humans,
)
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
    UserFactsBundle,
    find_relevant_contradiction,
    load_couple_facts,
    load_user_facts,
    mark_contradiction_surfaced,
)
from app.services.quotas import increment_message_count
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

    # ----- Suspension + quota -------------------------------------------------
    # §50: SSE responses can't bubble a regular HTTPException without
    # surfacing as an opaque 500, so we trap SuspendedUserError here and
    # ship a `suspended` SSE event instead of using the Depends-based
    # enforce_user helper that the JSON tools use.
    try:
        await assert_not_suspended(supabase, user_id=user_id)
    except SuspendedUserError as err:
        return _suspended_response(err)

    quota = await check_quota(supabase, user_id=user_id, scope="messages")
    if quota.exceeded:
        await analytics.track_server(
            "quota_429",
            user_id=user_id,
            data={"scope": "messages", "tier": quota.tier, "limit": quota.limit},
        )
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

    # ----- Group rooms (§9.3.4): AI intervenes only every 3rd human turn -----
    if conversation.get("group_room_id"):
        streak = await count_recent_consecutive_humans(
            supabase,
            conversation_id=conversation["id"],
        )
        if streak < AI_TURN_TAKING_THRESHOLD:
            log.info(
                "chat.group.deferred",
                group_id=conversation.get("group_room_id"),
                streak=streak,
                threshold=AI_TURN_TAKING_THRESHOLD,
            )
            return StreamingResponse(
                _group_saved_stream(
                    user_message_id=user_message_id,
                    streak=streak,
                    threshold=AI_TURN_TAKING_THRESHOLD,
                ),
                media_type="text/event-stream",
            )

    # ----- Assemble messages + stream ----------------------------------------
    system_blocks, fact_ids = await _build_system_blocks(
        supabase,
        user_id=user_id,
        persona_system_prompt=conversation["persona_system_prompt"],
        query_message=req.message,
        couple_link_id=conversation.get("couple_link_id"),
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

    # §21 trace context. Profile fetch is one extra row; the chat path
    # already touches profiles via quotas, so this is cheap.
    profile_res = (
        await supabase.table("profiles")
        .select("tier, locale")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    profile_row = row_or_none(profile_res.data if profile_res is not None else None) or {}
    trace_mode = conversation.get("mode") or req.mode
    trace_persona_slug = conversation.get("persona_slug") or req.persona_slug

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
            trace_name=f"{trace_mode}.{trace_persona_slug}"
            if trace_mode and trace_persona_slug
            else "chat.stream",
            mode=trace_mode if isinstance(trace_mode, str) else None,
            persona_slug=trace_persona_slug if isinstance(trace_persona_slug, str) else None,
            tier=profile_row.get("tier") if isinstance(profile_row.get("tier"), str) else None,
            locale=profile_row.get("locale") if isinstance(profile_row.get("locale"), str) else None,
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
    # §21 trace context — name/mode/persona/tier/locale resolved upstream.
    trace_name: str = "chat.stream",
    mode: str | None = None,
    persona_slug: str | None = None,
    tier: str | None = None,
    locale: str | None = None,
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
            metadata=build_trace_metadata(
                name=trace_name,
                user_id=user_id,
                session_id=conversation_id,
                mode=mode,
                persona_slug=persona_slug,
                tier=tier,
                locale=locale,
            ),
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

    # §20 chat_message_received — fires after we have an assistant turn
    # to record. Fact-extraction is queued separately below.
    await analytics.track_server(
        "chat_message_received",
        user_id=user_id,
        data={
            "conversation_id": conversation_id,
            "latency_ms": latency_ms,
            "cached_input_tokens": cached_tokens,
        },
    )

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
        # For group rooms (§9.3.4) any current group member is allowed.
        if row.get("user_id") != user_id:
            link_id = row.get("couple_link_id")
            group_id = row.get("group_room_id")
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
            if not allowed and group_id:
                # group_members is the source of truth for membership.
                # group_rooms.archived gates the whole row separately.
                room_res = (
                    await supabase.table("group_rooms")
                    .select("archived")
                    .eq("id", group_id)
                    .maybe_single()
                    .execute()
                )
                room_row = row_or_none(room_res.data) if room_res is not None else None
                if room_row is not None and not room_row.get("archived"):
                    member_res = (
                        await supabase.table("group_members")
                        .select("user_id")
                        .eq("group_id", group_id)
                        .eq("user_id", user_id)
                        .maybe_single()
                        .execute()
                    )
                    if member_res is not None and row_or_none(member_res.data) is not None:
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
            "couple_link_id": row.get("couple_link_id"),
            "group_room_id": row.get("group_room_id"),
            "mode": row.get("mode"),
            "persona_slug": persona.get("slug"),
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
    return {
        "id": new_id,
        "persona_system_prompt": persona["system_prompt"],
        "couple_link_id": couple_link_id,
        "mode": mode,
        "persona_slug": persona_slug,
    }


async def _load_persona_by_id(supabase: AsyncClient, persona_id: str) -> dict[str, Any]:
    res = (
        await supabase.table("personas")
        .select("id, slug, system_prompt")
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
    couple_link_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[int]]:
    """Assemble the system message as cache-controlled content blocks.

    §7.6 caching strategy splits the prompt into two segments:
      1. Anti-sycophant base + persona overlay — long-lived. Identical
         across turns of the same conversation, so OpenAI prompt caching
         auto-hits and Anthropic respects the cache_control marker.
      2. <user_facts> block — rotates per turn but still worth marking so
         repeat turns within a short window benefit.

    Couples conversations (§9.3.1): if a couple_link_id is set, we first
    try load_couple_facts (which calls the triple-consent-gated SQL
    function). If it returns a non-empty bundle, both partners' facts
    feed the mediator. If consent is missing the function raises and
    load_couple_facts returns empty — we fall back to single-user
    embedding retrieval so the mediator still sees the caller's own
    facts.

    Mirrors packages/ai/src/caching.ts buildSystemMessage().
    """

    facts: UserFactsBundle | None = None
    if couple_link_id:
        couple_bundle = await load_couple_facts(
            supabase,
            link_id=str(couple_link_id),
        )
        if couple_bundle.count > 0:
            facts = couple_bundle
            log.info(
                "chat.system_prompt.couple_facts",
                user_id=user_id,
                link_id=couple_link_id,
                fact_count=facts.count,
            )

    if facts is None:
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


async def _group_saved_stream(
    *,
    user_message_id: int,
    streak: int,
    threshold: int,
) -> AsyncIterator[bytes]:
    """SSE stream for group turns where the AI doesn't reply yet (§9.3.4).

    Emits a single `group_saved` event so the client can ack the turn,
    then closes with `done`. The Realtime subscription on `messages` is
    what makes the post visible to other members — this SSE just confirms
    persistence to the sender.
    """

    yield _sse_event(
        "group_saved",
        {
            "user_message_id": user_message_id,
            "consecutive_humans": streak,
            "ai_threshold": threshold,
        },
    )
    yield _sse_event("done", {"finish_reason": "group_no_ai_yet"})


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
    payload = quota_detail(quota, scope="messages")

    async def generator() -> AsyncIterator[bytes]:
        yield _sse_event("quota_exceeded", payload)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        status_code=429,
    )


def _suspended_response(err: SuspendedUserError) -> StreamingResponse:
    payload = err.detail if isinstance(err.detail, dict) else {"error": "user_suspended"}

    async def generator() -> AsyncIterator[bytes]:
        yield _sse_event("suspended", payload)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        status_code=403,
    )
