"""Negotiation Sparring service (CLAUDE.md §9.5.3).

Two endpoints:
    start_session(scenario_slug)   -> creates a mode='negotiate' conversation,
                                       writes the counterparty system prompt into
                                       conversations.metadata.system_prompt_override,
                                       inserts the opening counterparty message.
    run_critique(conversation_id)  -> reads the user's turns, sends to the LLM
                                       with CRITIQUE_PROMPT, persists the critique
                                       as an assistant message with kind='negotiation_critique'.

The chat route honors metadata.system_prompt_override transparently — see
routes/chat.py. Subsequent turns naturally use the scenario voice.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Annotated, Any

import structlog
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient

from app.prompts.anti_sycophant_base import ANTI_SYCOPHANT_BASE_PROMPT
from app.prompts.negotiation import CRITIQUE_PROMPT, SCENARIOS, Scenario
from app.services._db_typing import row_or_none, rows as _rows
from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


HOST_PERSONA_SLUG = "devils_advocate"
MAX_USER_TURNS_FOR_CRITIQUE = 30  # rough cap so a runaway session doesn't blow the prompt


class CritiqueResult(BaseModel):
    strengths: list[str] = Field(min_length=3, max_length=3)
    weaknesses: list[str] = Field(min_length=3, max_length=3)
    alternative: str = Field(min_length=20, max_length=1200)


@dataclass(slots=True)
class StartResult:
    conversation_id: str
    scenario: Scenario
    opening_message_id: int | None


@dataclass(slots=True)
class CritiqueRun:
    conversation_id: str
    scenario: Scenario
    critique: CritiqueResult
    assistant_message_id: int | None = None


class UnknownScenarioError(Exception):
    """Caller asked for a scenario slug that isn't in SCENARIOS."""


class NotANegotiationError(Exception):
    """Conversation isn't a negotiation session — critique not applicable."""


# ----- Scenario lookup ------------------------------------------------------


def get_scenario(slug: str) -> Scenario:
    scenario = SCENARIOS.get(slug)
    if scenario is None:
        raise UnknownScenarioError(slug)
    return scenario


def list_scenarios() -> list[Scenario]:
    return list(SCENARIOS.values())


# ----- DB helpers ----------------------------------------------------------


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
        raise RuntimeError("no_persona_rows_for_negotiation_host")
    return str(rows[0]["id"])


def _scenario_system_prompt(scenario: Scenario) -> str:
    """Compose the override that chat.py will use.

    The anti-sycophant base is intentionally OMITTED here — the scenario
    counterparty isn't Quarrel-the-persona, it's a roleplayed adversary.
    Layering anti-sycophant rules on top would make the counterparty
    behave out of character (e.g. interrogating the user about their own
    weakest point instead of negotiating against them).
    """

    return scenario.system_prompt


# ----- Start session -------------------------------------------------------


async def start_session(
    supabase: AsyncClient,
    *,
    user_id: str,
    scenario_slug: str,
) -> StartResult:
    scenario = get_scenario(scenario_slug)
    conversation_id = str(uuid.uuid4())
    host = await _load_host_persona_id(supabase)

    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "persona_id": host,
                "mode": "negotiate",
                "title": scenario.title,
                "metadata": {
                    "tool": "negotiation",
                    "scenario_slug": scenario.slug,
                    "scenario_title": scenario.title,
                    "counterparty": scenario.counterparty,
                    "system_prompt_override": _scenario_system_prompt(scenario),
                },
            }
        )
        .execute()
    )

    # Insert the counterparty's opening as the first assistant message so
    # the user lands on /chat/[id] with something to react to.
    opening_res = (
        await supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "user_id": None,
                "role": "assistant",
                "content": scenario.opening_line,
                "safety_verdict": "safe",
                "model": QUARREL_ARGUE,
                "metadata": {"kind": "negotiation_opening"},
            }
        )
        .execute()
    )
    inserted = _rows(opening_res.data)
    opening_id = int(inserted[0]["id"]) if inserted else None

    return StartResult(
        conversation_id=conversation_id,
        scenario=scenario,
        opening_message_id=opening_id,
    )


# ----- Critique ------------------------------------------------------------


async def _load_session(supabase: AsyncClient, conversation_id: str) -> dict[str, Any]:
    res = (
        await supabase.table("conversations")
        .select("id, user_id, mode, metadata")
        .eq("id", conversation_id)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        raise NotANegotiationError("conversation_not_found")
    if row.get("mode") != "negotiate":
        raise NotANegotiationError("not_a_negotiation")
    return row


async def _load_user_turns(
    supabase: AsyncClient, conversation_id: str
) -> list[str]:
    res = (
        await supabase.table("messages")
        .select("content, role, created_at")
        .eq("conversation_id", conversation_id)
        .eq("role", "user")
        .order("created_at", desc=False)
        .limit(MAX_USER_TURNS_FOR_CRITIQUE)
        .execute()
    )
    rows = _rows(res.data)
    return [str(r["content"]) for r in rows]


def _format_user_turns(turns: list[str]) -> str:
    if not turns:
        return "(no user turns recorded)"
    return "\n".join(f"{i}. {t}" for i, t in enumerate(turns, start=1))


async def generate_critique(
    *,
    scenario: Scenario,
    user_turns: list[str],
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> CritiqueResult | None:
    """One LLM call. None on any defensive path."""

    if not user_turns:
        return None

    llm = client or get_llm_client()
    body = (
        f"<scenario>{scenario.title}</scenario>\n"
        f"<counterparty>{scenario.counterparty}</counterparty>\n"
        "<user_turns>\n"
        f"{_format_user_turns(user_turns)}\n"
        "</user_turns>"
    )

    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": CRITIQUE_PROMPT},
                {"role": "user", "content": body},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            user=user_id,
            metadata=build_trace_metadata(
                name="negotiation.critique",
                user_id=user_id,
                mode="negotiation",
                extra={"scenario_slug": scenario.slug},
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("negotiation.critique.llm_error", error=str(err))
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
        log.warning("negotiation.critique.json_decode_failed", raw=raw[:200])
        return None
    try:
        return CritiqueResult.model_validate(parsed)
    except ValidationError as err:
        log.warning("negotiation.critique.schema_invalid", error=str(err))
        return None


def _render_critique_content(critique: CritiqueResult) -> str:
    lines = ["## Strengths"]
    for i, s in enumerate(critique.strengths, start=1):
        lines.append(f"{i}. {s}")
    lines.append("")
    lines.append("## Weaknesses")
    for i, w in enumerate(critique.weaknesses, start=1):
        lines.append(f"{i}. {w}")
    lines.append("")
    lines.append("## What to try next time")
    lines.append(critique.alternative)
    return "\n".join(lines)


async def persist_critique(
    supabase: AsyncClient,
    *,
    conversation_id: str,
    critique: CritiqueResult,
) -> int | None:
    res = (
        await supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "user_id": None,
                "role": "assistant",
                "content": _render_critique_content(critique),
                "safety_verdict": "safe",
                "model": QUARREL_ARGUE,
                "metadata": {
                    "kind": "negotiation_critique",
                    "strengths": critique.strengths,
                    "weaknesses": critique.weaknesses,
                    "alternative": critique.alternative,
                },
            }
        )
        .execute()
    )
    inserted = _rows(res.data)
    return int(inserted[0]["id"]) if inserted else None


async def run_critique(
    supabase: AsyncClient,
    *,
    user_id: str,
    conversation_id: str,
    client: LiteLLMClient | None = None,
) -> CritiqueRun | None:
    session = await _load_session(supabase, conversation_id)
    if session.get("user_id") != user_id:
        raise NotANegotiationError("not_session_owner")

    metadata = session.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise NotANegotiationError("metadata_missing")
    scenario_slug = metadata.get("scenario_slug")
    if not isinstance(scenario_slug, str):
        raise NotANegotiationError("scenario_slug_missing")
    scenario = get_scenario(scenario_slug)

    user_turns = await _load_user_turns(supabase, conversation_id)
    critique = await generate_critique(
        scenario=scenario,
        user_turns=user_turns,
        client=client,
        user_id=user_id,
    )
    if critique is None:
        return None

    assistant_message_id = await persist_critique(
        supabase,
        conversation_id=conversation_id,
        critique=critique,
    )

    return CritiqueRun(
        conversation_id=conversation_id,
        scenario=scenario,
        critique=critique,
        assistant_message_id=assistant_message_id,
    )


__all__ = [
    "CritiqueResult",
    "CritiqueRun",
    "NotANegotiationError",
    "Scenario",
    "StartResult",
    "UnknownScenarioError",
    "generate_critique",
    "get_scenario",
    "list_scenarios",
    "persist_critique",
    "run_critique",
    "start_session",
]
