"""Drill Sergeant cron (CLAUDE.md §9.5.4).

For every active streak, compute days since last_checkin_at. If the gap
matches one of the §9.5.4 escalation tiers (1/3/7/14), generate a
tier-specific roast via quarrel-cheap and append it to the user's
stable "Drill Sergeant" conversation. Dedupe per (streak_id, tier,
since_checkin_at) via message metadata so the same break only fires
each tier once.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog
from supabase import AsyncClient

from app.prompts.drill_sergeant import ESCALATION_TIERS, TIER_PROMPTS
from app.services._db_typing import row_or_none, rows as _rows
from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services.llm import (
    QUARREL_CHEAP,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


MAX_ROAST_CHARS = 280
MIN_ROAST_CHARS = 30
HOST_PERSONA_SLUG = "devils_advocate"  # fallback when the_drill_sergeant isn't seeded


@dataclass(slots=True)
class StreakCandidate:
    streak_id: int
    user_id: str
    habit: str
    last_checkin_at: date
    longest_streak: int
    tier: int  # 1 / 3 / 7 / 14


@dataclass(slots=True)
class DrillRun:
    streak_id: int
    tier: int
    text: str
    conversation_id: str
    message_id: int


# ----- Eligibility scan ----------------------------------------------------


async def find_streaks_needing_nudge(
    supabase: AsyncClient,
    *,
    today: date,
) -> list[StreakCandidate]:
    """Streaks whose `today - last_checkin_at` matches an escalation tier."""

    res = (
        await supabase.table("streaks")
        .select("id, user_id, habit, last_checkin_at, longest_streak")
        .not_.is_("last_checkin_at", "null")
        .limit(1000)
        .execute()
    )
    out: list[StreakCandidate] = []
    for row in _rows(res.data):
        raw = row.get("last_checkin_at")
        if not isinstance(raw, str):
            continue
        try:
            last = date.fromisoformat(raw)
        except ValueError:
            continue
        gap = (today - last).days
        if gap in ESCALATION_TIERS:
            out.append(
                StreakCandidate(
                    streak_id=int(row["id"]),
                    user_id=str(row["user_id"]),
                    habit=str(row.get("habit") or ""),
                    last_checkin_at=last,
                    longest_streak=int(row.get("longest_streak") or 0),
                    tier=gap,
                )
            )
    return out


# ----- Dedupe --------------------------------------------------------------


async def already_fired(
    supabase: AsyncClient,
    *,
    candidate: StreakCandidate,
) -> bool:
    """Has this (streak, tier, last_checkin_at) already been roasted?

    We look up the user's Drill Sergeant conversation and scan recent
    drill_sergeant messages for a matching metadata signature. Since
    streaks reset on check-in (last_checkin_at moves forward) the
    signature naturally invalidates after a new check-in.
    """

    res = (
        await supabase.table("messages")
        .select("id, metadata, created_at")
        .eq("user_id", None)
        .eq("role", "assistant")
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    target = candidate.last_checkin_at.isoformat()
    for row in _rows(res.data):
        meta = row.get("metadata")
        if not isinstance(meta, dict):
            continue
        if meta.get("kind") != "drill_sergeant":
            continue
        if (
            meta.get("streak_id") == candidate.streak_id
            and meta.get("tier") == candidate.tier
            and meta.get("since_checkin_at") == target
        ):
            return True
    return False


# ----- Conversation lookup -------------------------------------------------


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
        raise RuntimeError("no_persona_rows_for_drill_sergeant_host")
    return str(rows[0]["id"])


async def get_or_create_drill_sergeant_conversation(
    supabase: AsyncClient,
    *,
    user_id: str,
) -> str:
    """Stable per-user "Drill Sergeant" conversation. Found by mode +
    metadata.kind to keep it disjoint from the user's regular roast
    conversations (Daily Roast lives in its own — see daily_roast.py).
    """

    res = (
        await supabase.table("conversations")
        .select("id, metadata, archived")
        .eq("user_id", user_id)
        .eq("mode", "drill_sergeant")
        .eq("archived", False)
        .limit(20)
        .execute()
    )
    for row in _rows(res.data):
        meta = row.get("metadata")
        if isinstance(meta, dict) and meta.get("kind") == "drill_sergeant":
            return str(row["id"])

    conversation_id = str(uuid.uuid4())
    host = await _load_host_persona_id(supabase)
    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "persona_id": host,
                "mode": "drill_sergeant",
                "title": "Drill Sergeant",
                "archived": False,
                "metadata": {"kind": "drill_sergeant"},
            }
        )
        .execute()
    )
    return conversation_id


# ----- Generation ----------------------------------------------------------


async def generate_drill_message(
    candidate: StreakCandidate,
    *,
    client: LiteLLMClient | None = None,
) -> str | None:
    llm = client or get_llm_client()
    prompt = TIER_PROMPTS.get(candidate.tier)
    if prompt is None:
        return None

    body = (
        f"<habit>{candidate.habit or 'their tracked habit'}</habit>\n"
        f"<missed_days>{candidate.tier}</missed_days>\n"
        f"<streak_lost>{candidate.longest_streak}</streak_lost>"
    )

    try:
        response = await llm.chat(
            model=QUARREL_CHEAP,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": body},
            ],
            temperature=0.7,
            max_tokens=180,
            user=candidate.user_id,
            metadata=build_trace_metadata(
                name=f"drill_sergeant.tier_{candidate.tier}",
                user_id=candidate.user_id,
                mode="drill_sergeant",
                extra={"escalation_tier": candidate.tier},
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning(
            "drill_sergeant.llm_error",
            streak_id=candidate.streak_id,
            tier=candidate.tier,
            error=str(err),
        )
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
        return None
    if len(text) > MAX_ROAST_CHARS:
        text = text[:MAX_ROAST_CHARS].rstrip()
    return text


# ----- Persistence ---------------------------------------------------------


async def persist_drill_message(
    supabase: AsyncClient,
    *,
    candidate: StreakCandidate,
    text: str,
    conversation_id: str,
) -> int | None:
    res = (
        await supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "user_id": None,
                "role": "assistant",
                "content": text,
                "safety_verdict": "safe",
                "model": QUARREL_CHEAP,
                "metadata": {
                    "kind": "drill_sergeant",
                    "streak_id": candidate.streak_id,
                    "habit": candidate.habit,
                    "tier": candidate.tier,
                    "since_checkin_at": candidate.last_checkin_at.isoformat(),
                },
            }
        )
        .execute()
    )
    inserted = _rows(res.data)
    return int(inserted[0]["id"]) if inserted else None


# ----- Orchestration -------------------------------------------------------


async def deliver(
    supabase: AsyncClient,
    *,
    candidate: StreakCandidate,
    client: LiteLLMClient | None = None,
) -> DrillRun | None:
    if await already_fired(supabase, candidate=candidate):
        log.info(
            "drill_sergeant.dedupe",
            streak_id=candidate.streak_id,
            tier=candidate.tier,
        )
        return None

    text = await generate_drill_message(candidate, client=client)
    if text is None:
        return None

    conversation_id = await get_or_create_drill_sergeant_conversation(
        supabase,
        user_id=candidate.user_id,
    )
    message_id = await persist_drill_message(
        supabase,
        candidate=candidate,
        text=text,
        conversation_id=conversation_id,
    )
    if message_id is None:
        return None
    return DrillRun(
        streak_id=candidate.streak_id,
        tier=candidate.tier,
        text=text,
        conversation_id=conversation_id,
        message_id=message_id,
    )


async def run_today(
    *,
    today: date | None = None,
    client: LiteLLMClient | None = None,
    supabase: AsyncClient | None = None,
) -> dict[str, int]:
    sb = supabase or await get_supabase()
    cutoff = today or datetime.now(UTC).date()
    candidates = await find_streaks_needing_nudge(sb, today=cutoff)

    delivered = 0
    skipped = 0
    for c in candidates:
        run = await deliver(sb, candidate=c, client=client)
        if run is None:
            skipped += 1
        else:
            delivered += 1

    log.info(
        "drill_sergeant.batch.done",
        today=cutoff.isoformat(),
        candidates=len(candidates),
        delivered=delivered,
        skipped=skipped,
    )
    return {
        "candidates": len(candidates),
        "delivered": delivered,
        "skipped": skipped,
    }


__all__ = [
    "DrillRun",
    "MAX_ROAST_CHARS",
    "MIN_ROAST_CHARS",
    "StreakCandidate",
    "already_fired",
    "deliver",
    "find_streaks_needing_nudge",
    "generate_drill_message",
    "get_or_create_drill_sergeant_conversation",
    "persist_drill_message",
    "run_today",
]
