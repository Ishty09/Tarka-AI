"""Breakup Analyzer service (CLAUDE.md §9.3.3).

Single quarrel-argue call producing a structured analysis of a recent
text thread. Persists as a conversation (mode='custom') with metadata
flagging it as the breakup-analyzer tool so the user can find it in
their conversation list.

Quota: counts as 3 messages (§9.3.3) — the route increments accordingly.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import structlog
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient

from app.prompts.breakup_analyzer import BREAKUP_ANALYZER_PROMPT
from app.services._db_typing import row_or_none, rows as _rows
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)


THREAD_MAX_CHARS = 5000  # §9.3.3 cap
DURATION_MAX_CHARS = 80
HOST_PERSONA_SLUG = "devils_advocate"

# Counts as N messages for quota purposes (§9.3.3).
QUOTA_COST = 3


AttachmentStyle = Literal["avoidant", "anxious", "secure", "disorganized"]
Likelihood = Literal["low", "medium", "high"]
MessageIntent = Literal["repair", "end"]


class AttachmentDynamics(BaseModel):
    user: AttachmentStyle
    partner: AttachmentStyle
    summary: str = Field(min_length=10, max_length=600)


class SuggestedMessage(BaseModel):
    intent: MessageIntent
    text: str = Field(min_length=30, max_length=2400)


class BreakupAnalyzerResult(BaseModel):
    attachment_dynamics: AttachmentDynamics
    reconciliation_likelihood: Likelihood
    reconciliation_reasoning: str = Field(min_length=10, max_length=800)
    missing_things: list[str] = Field(min_length=3, max_length=3)
    suggested_message: SuggestedMessage


@dataclass(slots=True)
class BreakupAnalyzerRun:
    text_thread: str
    duration: str
    user_age: int
    partner_age: int
    intent: MessageIntent
    result: BreakupAnalyzerResult
    conversation_id: str | None = None
    assistant_message_id: int | None = None


# ----- Prompt input ---------------------------------------------------------


def _format_input(
    *,
    text_thread: str,
    duration: str,
    user_age: int,
    partner_age: int,
    intent: MessageIntent,
) -> str:
    return (
        "<context>\n"
        f"duration: {duration}\n"
        f"user_age: {user_age}\n"
        f"partner_age: {partner_age}\n"
        f"intent: {intent}\n"
        "</context>\n\n"
        "<thread>\n"
        f"{text_thread}\n"
        "</thread>"
    )


# ----- LLM call -------------------------------------------------------------


async def generate_breakup_analysis(
    *,
    text_thread: str,
    duration: str,
    user_age: int,
    partner_age: int,
    intent: MessageIntent,
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> BreakupAnalyzerResult | None:
    if not text_thread.strip():
        return None

    llm = client or get_llm_client()
    body = _format_input(
        text_thread=text_thread,
        duration=duration,
        user_age=user_age,
        partner_age=partner_age,
        intent=intent,
    )

    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": BREAKUP_ANALYZER_PROMPT},
                {"role": "user", "content": body},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
            user=user_id,
            metadata={
                "generation_name": "breakup_analyzer",
                "trace_user_id": user_id,
                "tags": ["breakup_analyzer"],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("breakup_analyzer.llm_error", user_id=user_id, error=str(err))
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
        log.warning("breakup_analyzer.json_decode_failed", raw=raw[:200])
        return None
    try:
        return BreakupAnalyzerResult.model_validate(parsed)
    except ValidationError as err:
        log.warning("breakup_analyzer.schema_invalid", error=str(err))
        return None


# ----- Persist + run -------------------------------------------------------


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
        raise RuntimeError("no_persona_rows_for_breakup_analyzer_host")
    return str(rows[0]["id"])


def _render_assistant_content(result: BreakupAnalyzerResult) -> str:
    dyn = result.attachment_dynamics
    lines = [
        "## Attachment dynamics",
        f"- **You:** {dyn.user}",
        f"- **Partner:** {dyn.partner}",
        f"- {dyn.summary}",
        "",
        f"## Reconciliation likelihood: {result.reconciliation_likelihood}",
        result.reconciliation_reasoning,
        "",
        "## What you're missing",
    ]
    for i, m in enumerate(result.missing_things, start=1):
        lines.append(f"{i}. {m}")
    lines.append("")
    lines.append(
        f"## Suggested message ({result.suggested_message.intent})"
    )
    lines.append(result.suggested_message.text)
    return "\n".join(lines)


async def persist_breakup_analyzer_run(
    supabase: AsyncClient,
    *,
    user_id: str,
    run: BreakupAnalyzerRun,
) -> BreakupAnalyzerRun:
    conversation_id = str(uuid.uuid4())
    host = await _load_host_persona_id(supabase)

    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "persona_id": host,
                "mode": "custom",  # §9.3.3 prescribes custom + tool marker
                "title": "Breakup analyzer",
                "metadata": {
                    "tool": "breakup_analyzer",
                    "duration": run.duration,
                    "user_age": run.user_age,
                    "partner_age": run.partner_age,
                    "intent": run.intent,
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
                "content": run.text_thread,
                "safety_verdict": "safe",
                "metadata": {"kind": "breakup_thread"},
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
                    "kind": "breakup_analysis",
                    "attachment_dynamics": run.result.attachment_dynamics.model_dump(),
                    "reconciliation_likelihood": run.result.reconciliation_likelihood,
                    "reconciliation_reasoning": run.result.reconciliation_reasoning,
                    "missing_things": run.result.missing_things,
                    "suggested_message": run.result.suggested_message.model_dump(),
                },
            }
        )
        .execute()
    )
    inserted = _rows(assistant_res.data)
    run.conversation_id = conversation_id
    run.assistant_message_id = int(inserted[0]["id"]) if inserted else None
    return run


async def run_breakup_analyzer(
    supabase: AsyncClient,
    *,
    user_id: str,
    text_thread: str,
    duration: str,
    user_age: int,
    partner_age: int,
    intent: MessageIntent,
    client: LiteLLMClient | None = None,
) -> BreakupAnalyzerRun | None:
    result = await generate_breakup_analysis(
        text_thread=text_thread,
        duration=duration,
        user_age=user_age,
        partner_age=partner_age,
        intent=intent,
        client=client,
        user_id=user_id,
    )
    if result is None:
        return None
    run = BreakupAnalyzerRun(
        text_thread=text_thread,
        duration=duration,
        user_age=user_age,
        partner_age=partner_age,
        intent=intent,
        result=result,
    )
    return await persist_breakup_analyzer_run(supabase, user_id=user_id, run=run)


__all__ = [
    "AttachmentDynamics",
    "AttachmentStyle",
    "BreakupAnalyzerResult",
    "BreakupAnalyzerRun",
    "DURATION_MAX_CHARS",
    "Likelihood",
    "MessageIntent",
    "QUOTA_COST",
    "SuggestedMessage",
    "THREAD_MAX_CHARS",
    "generate_breakup_analysis",
    "persist_breakup_analyzer_run",
    "run_breakup_analyzer",
]
