"""Multi-Agent Council orchestration (CLAUDE.md §9.1.2).

Six LLM calls per run: five councilors in parallel (each prompted with the
anti-sycophant base + their persona overlay), then the Judge synthesises.
Failures on individual councilors are tolerated — the Judge gets whoever
came back. A total wipeout (zero councilors returned) raises so the route
can surface the failure instead of persisting an empty run.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient

from app.prompts.anti_sycophant_base import ANTI_SYCOPHANT_BASE_PROMPT
from app.prompts.council import COUNCIL_SLUGS, JUDGE_SYSTEM_PROMPT
from app.services._db_typing import rows as _rows
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)


# Cap each councilor's response so the judge prompt fits comfortably in
# context — §9.1.2 calls for ~200 words per member.
MAX_COUNCILOR_TOKENS = 350


class JudgeVerdict(BaseModel):
    """Parsed §9.1.2 verdict card payload."""

    conditions_for: list[str] = Field(default_factory=list, max_length=5)
    conditions_against: list[str] = Field(default_factory=list, max_length=5)
    missing_information: list[str] = Field(default_factory=list, max_length=5)
    confidence: Annotated[int, Field(ge=0, le=10)]
    verdict: str = Field(min_length=1, max_length=2000)


@dataclass(slots=True)
class CouncilReply:
    slug: str
    text: str | None
    error: str | None = None


@dataclass(slots=True)
class CouncilRun:
    """In-memory result of one council session.

    `conversation_id` and `assistant_message_id` are set after persistence.
    """

    dilemma: str
    replies: list[CouncilReply]
    verdict: JudgeVerdict
    conversation_id: str | None = None
    assistant_message_id: int | None = None


class CouncilWipeoutError(Exception):
    """All five councilors failed. Caller decides how to surface this."""


# ----- Persona loading -------------------------------------------------------


async def load_council_personas(supabase: AsyncClient) -> dict[str, dict[str, Any]]:
    """Pull the 5 §10.1 council personas by slug.

    Returns slug → row dict. Missing personas are silently absent; callers
    decide whether to abort or proceed with a reduced council.
    """

    res = (
        await supabase.table("personas")
        .select("id, slug, system_prompt")
        .in_("slug", list(COUNCIL_SLUGS))
        .execute()
    )
    return {str(row["slug"]): row for row in _rows(res.data)}


# ----- Per-councilor call ----------------------------------------------------


async def _run_councilor(
    *,
    llm: LiteLLMClient,
    slug: str,
    persona_system_prompt: str,
    dilemma: str,
    user_id: str | None,
) -> CouncilReply:
    system = f"{ANTI_SYCOPHANT_BASE_PROMPT}\n\n{persona_system_prompt}\n\nKeep your reply under 200 words."
    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": dilemma},
            ],
            temperature=0.5,
            max_tokens=MAX_COUNCILOR_TOKENS,
            user=user_id,
            metadata={
                "generation_name": f"council.{slug}",
                "trace_user_id": user_id,
                "tags": ["council", slug],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("council.member.failed", slug=slug, error=str(err))
        return CouncilReply(slug=slug, text=None, error=str(err))

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as err:
        return CouncilReply(slug=slug, text=None, error=f"bad_shape:{err}")

    if isinstance(content, list):
        content = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if not isinstance(content, str) or not content.strip():
        return CouncilReply(slug=slug, text=None, error="empty_content")

    return CouncilReply(slug=slug, text=content.strip())


async def run_council_members(
    *,
    personas: dict[str, dict[str, Any]],
    dilemma: str,
    client: LiteLLMClient,
    user_id: str | None = None,
) -> list[CouncilReply]:
    """Fan out 5 calls in parallel. Order matches COUNCIL_SLUGS."""

    tasks = []
    for slug in COUNCIL_SLUGS:
        persona = personas.get(slug)
        if persona is None:
            tasks.append(_missing_reply(slug))
            continue
        tasks.append(
            _run_councilor(
                llm=client,
                slug=slug,
                persona_system_prompt=str(persona["system_prompt"]),
                dilemma=dilemma,
                user_id=user_id,
            )
        )
    return await asyncio.gather(*tasks)


async def _missing_reply(slug: str) -> CouncilReply:
    return CouncilReply(slug=slug, text=None, error="persona_not_seeded")


# ----- Judge -----------------------------------------------------------------


async def run_judge(
    *,
    dilemma: str,
    replies: list[CouncilReply],
    client: LiteLLMClient,
    user_id: str | None = None,
) -> JudgeVerdict | None:
    """One LLM call synthesising the council replies. None on any failure."""

    payload = _format_judge_input(dilemma, replies)

    try:
        response = await client.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            user=user_id,
            metadata={
                "generation_name": "council.judge",
                "trace_user_id": user_id,
                "tags": ["council", "judge"],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("council.judge.llm_error", error=str(err))
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
        log.warning("council.judge.json_decode_failed", raw=raw[:200])
        return None
    try:
        return JudgeVerdict.model_validate(parsed)
    except ValidationError as err:
        log.warning("council.judge.schema_invalid", error=str(err))
        return None


def _format_judge_input(dilemma: str, replies: list[CouncilReply]) -> str:
    parts = [f"<dilemma>\n{dilemma}\n</dilemma>"]
    for reply in replies:
        if reply.text:
            parts.append(f'<council slug="{reply.slug}">\n{reply.text}\n</council>')
    return "\n\n".join(parts)


# ----- Persist + run ---------------------------------------------------------


async def persist_council_run(
    supabase: AsyncClient,
    *,
    user_id: str,
    run: CouncilRun,
) -> CouncilRun:
    """Create a conversation + user message + assistant verdict.

    The 5 council member replies are stored in messages.metadata so the UI
    can pull a full record without joining a side table.
    """

    conversation_id = str(uuid.uuid4())

    judge_persona = await _load_judge_persona_id(supabase)

    # Insert the conversation. We use the judge persona as the "host"
    # persona_id because conversations require a non-null FK and the judge
    # is what speaks the final verdict.
    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "persona_id": judge_persona,
                "mode": "council",
                "metadata": {
                    "roster": list(COUNCIL_SLUGS),
                    "verdict_confidence": run.verdict.confidence,
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
                "content": run.dilemma,
                "safety_verdict": "safe",
            }
        )
        .execute()
    )

    council_payload = [
        {"slug": r.slug, "text": r.text, "error": r.error} for r in run.replies
    ]
    verdict_payload: dict[str, Any] = run.verdict.model_dump()

    assistant_res = (
        await supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "user_id": None,
                "role": "assistant",
                "content": run.verdict.verdict,
                "safety_verdict": "safe",
                "model": QUARREL_ARGUE,
                "metadata": {
                    "kind": "council_verdict",
                    "council": council_payload,
                    "verdict": verdict_payload,
                },
            }
        )
        .execute()
    )
    inserted = _rows(assistant_res.data)
    run.conversation_id = conversation_id
    run.assistant_message_id = int(inserted[0]["id"]) if inserted else None
    return run


async def _load_judge_persona_id(supabase: AsyncClient) -> str:
    """The judge isn't a §10.1 persona — we host the council under the_skeptic
    because it carries the synthesis-friendly voice. Falls back to the first
    persona returned if the canonical row is missing (defensive — should
    never happen in a seeded environment).
    """

    res = (
        await supabase.table("personas")
        .select("id")
        .eq("slug", "the_skeptic")
        .maybe_single()
        .execute()
    )
    row = res.data if res else None
    if isinstance(row, dict) and row.get("id"):
        return str(row["id"])

    fallback = await supabase.table("personas").select("id").limit(1).execute()
    rows = _rows(fallback.data)
    if not rows:
        raise CouncilWipeoutError("no_persona_rows_for_council_host")
    return str(rows[0]["id"])


async def run_council(
    supabase: AsyncClient,
    *,
    user_id: str,
    dilemma: str,
    client: LiteLLMClient | None = None,
) -> CouncilRun:
    """End-to-end: load → fan-out → judge → persist.

    Raises CouncilWipeoutError if no council member returned text — the
    route handler turns that into a 502 / retry.
    """

    llm = client or get_llm_client()
    personas = await load_council_personas(supabase)

    replies = await run_council_members(
        personas=personas,
        dilemma=dilemma,
        client=llm,
        user_id=user_id,
    )

    if not any(r.text for r in replies):
        log.warning("council.wipeout", user_id=user_id)
        raise CouncilWipeoutError("all_councilors_failed")

    verdict = await run_judge(
        dilemma=dilemma,
        replies=replies,
        client=llm,
        user_id=user_id,
    )
    if verdict is None:
        # Synthesise a defensive verdict instead of crashing the run — the
        # councilor replies are still useful to the user.
        verdict = JudgeVerdict(
            conditions_for=[],
            conditions_against=[],
            missing_information=["Judge synthesis failed; review the councilor replies directly."],
            confidence=0,
            verdict="The council weighed in but the synthesis call failed. Read each councilor's argument and call it yourself.",
        )

    run = CouncilRun(dilemma=dilemma, replies=replies, verdict=verdict)
    return await persist_council_run(supabase, user_id=user_id, run=run)


__all__ = [
    "COUNCIL_SLUGS",
    "CouncilReply",
    "CouncilRun",
    "CouncilWipeoutError",
    "JudgeVerdict",
    "load_council_personas",
    "persist_council_run",
    "run_council",
    "run_council_members",
    "run_judge",
]
