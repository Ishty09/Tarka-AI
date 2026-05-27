"""Mirror Mode weekly report generator (CLAUDE.md §9.4.2).

For each Pro/Max user with activity in the period, aggregate their messages
and freshly-extracted facts, send to quarrel-argue, parse JSON, persist a
row in mirror_reports.

Free-tier users are skipped — §8.1 says free is read-only past reports.
The mirror_reports.unique(user_id, period_start) constraint means a re-run
for the same period is a no-op (idempotent).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient

from app.prompts.mirror_mode import MIRROR_MODE_PROMPT
from app.services._db_typing import rows as _rows
from app.services.email import send_email
from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)
from app.services.push import deliver_to_user
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


# Tiers eligible for new report generation. Free is read-only past reports
# per §8.1; admin tier override isn't a concept yet.
ELIGIBLE_TIERS = {"pro", "max"}

# Cap on messages fed into the prompt. A pro-tier max user sends 200/day ×
# 7 = 1400 — too many. Take the most recent 200 and let the older ones
# fade. Tokens-per-message averages ~50, so 200 messages ≈ 10k tokens of
# user input, which fits comfortably alongside the prompt and the
# extracted-facts list.
MAX_MESSAGES_IN_WINDOW = 200
MAX_FACTS_IN_WINDOW = 100


# ----- Parsed-LLM models -----------------------------------------------------


class MirrorPattern(BaseModel):
    theme: str = Field(min_length=1, max_length=120)
    support: str = Field(min_length=1, max_length=400)


class MirrorDodge(BaseModel):
    topic: str = Field(min_length=1, max_length=120)
    observed: str = Field(min_length=1, max_length=400)


class MirrorReportPayload(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)
    patterns: list[MirrorPattern] = Field(default_factory=list, max_length=5)
    dodges: list[MirrorDodge] = Field(default_factory=list, max_length=3)


@dataclass(slots=True)
class GenerationResult:
    user_id: str
    inserted: bool
    reason: str | None = None


# ----- LLM call --------------------------------------------------------------


async def generate_report(
    *,
    user_messages: list[str],
    facts: list[str],
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> MirrorReportPayload | None:
    """One LLM call to produce the structured report. None on any failure."""

    if not user_messages and not facts:
        return None

    llm = client or get_llm_client()
    payload = _format_input(user_messages, facts)

    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": MIRROR_MODE_PROMPT},
                {"role": "user", "content": payload},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
            user=user_id,
            metadata=build_trace_metadata(
                name="mirror_mode",
                user_id=user_id,
                mode="mirror_mode",
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("mirror.generate.llm_error", user_id=user_id, error=str(err))
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
        log.warning("mirror.generate.json_decode_failed", raw=raw[:200])
        return None
    try:
        return MirrorReportPayload.model_validate(parsed)
    except ValidationError as err:
        log.warning("mirror.generate.schema_invalid", error=str(err))
        return None


def _format_input(user_messages: list[str], facts: list[str]) -> str:
    msg_block = "\n".join(f"- {m}" for m in user_messages[-MAX_MESSAGES_IN_WINDOW:])
    fact_block = "\n".join(f"- {f}" for f in facts[-MAX_FACTS_IN_WINDOW:])
    return (
        "<messages>\n"
        f"{msg_block or '(none)'}\n"
        "</messages>\n\n"
        "<facts>\n"
        f"{fact_block or '(none)'}\n"
        "</facts>"
    )


# ----- DB helpers ------------------------------------------------------------


async def fetch_window_signals(
    supabase: AsyncClient,
    user_id: str,
    *,
    period_start: datetime,
    period_end: datetime,
) -> tuple[list[str], list[str]]:
    """Return (user_messages, extracted_facts) inside [period_start, period_end).

    Reads `messages.content` for role='user' and safety_verdict='safe' (we
    don't want refused turns colouring the narrative), and `user_facts.fact`
    inserted in the same window.
    """

    msg_res = (
        await supabase.table("messages")
        .select("content")
        .eq("user_id", user_id)
        .eq("role", "user")
        .eq("safety_verdict", "safe")
        .gte("created_at", period_start.isoformat())
        .lt("created_at", period_end.isoformat())
        .order("created_at", desc=False)
        .limit(MAX_MESSAGES_IN_WINDOW * 2)
        .execute()
    )
    messages_list = [str(r["content"]) for r in _rows(msg_res.data)]

    fact_res = (
        await supabase.table("user_facts")
        .select("fact")
        .eq("user_id", user_id)
        .gte("created_at", period_start.isoformat())
        .lt("created_at", period_end.isoformat())
        .order("created_at", desc=False)
        .limit(MAX_FACTS_IN_WINDOW * 2)
        .execute()
    )
    facts_list = [str(r["fact"]) for r in _rows(fact_res.data)]

    return messages_list, facts_list


async def find_eligible_users(
    supabase: AsyncClient,
    *,
    period_start: datetime,
    period_end: datetime,
) -> list[dict[str, Any]]:
    """Distinct (user_id, tier) for users with at least one safe user message
    in the window AND tier in ELIGIBLE_TIERS.
    """

    msg_res = (
        await supabase.table("messages")
        .select("user_id")
        .eq("role", "user")
        .eq("safety_verdict", "safe")
        .gte("created_at", period_start.isoformat())
        .lt("created_at", period_end.isoformat())
        .execute()
    )
    user_ids = list({str(r["user_id"]) for r in _rows(msg_res.data) if r.get("user_id")})
    if not user_ids:
        return []

    profile_res = (
        await supabase.table("profiles")
        .select("id, tier")
        .in_("id", user_ids)
        .execute()
    )
    return [
        row
        for row in _rows(profile_res.data)
        if str(row.get("tier", "free")) in ELIGIBLE_TIERS
    ]


async def persist_report(
    supabase: AsyncClient,
    *,
    user_id: str,
    period_start: date,
    period_end: date,
    payload: MirrorReportPayload,
) -> bool:
    """Insert the row idempotently. Returns True if a new row was created.

    mirror_reports has UNIQUE(user_id, period_start) so a same-window re-
    run is silently dropped.
    """

    row: dict[str, Any] = {
        "user_id": user_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "summary": payload.summary,
        "patterns": [p.model_dump() for p in payload.patterns],
        "dodges": [d.model_dump() for d in payload.dodges],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    try:
        res = (
            await supabase.table("mirror_reports")
            .upsert(row, on_conflict="user_id,period_start", ignore_duplicates=True)
            .execute()
        )
    except Exception as err:  # noqa: BLE001 — best-effort path
        log.warning(
            "mirror.persist.failed",
            user_id=user_id,
            period_start=period_start.isoformat(),
            error=str(err),
        )
        return False
    return bool(_rows(res.data))


# ----- Orchestration ---------------------------------------------------------


async def run_for_user(
    supabase: AsyncClient,
    *,
    user_id: str,
    period_start: datetime,
    period_end: datetime,
    client: LiteLLMClient | None = None,
) -> GenerationResult:
    messages, facts = await fetch_window_signals(
        supabase,
        user_id,
        period_start=period_start,
        period_end=period_end,
    )

    if not messages:
        return GenerationResult(user_id=user_id, inserted=False, reason="no_messages")

    payload = await generate_report(
        user_messages=messages,
        facts=facts,
        client=client,
        user_id=user_id,
    )
    if payload is None:
        return GenerationResult(user_id=user_id, inserted=False, reason="llm_failed")

    inserted = await persist_report(
        supabase,
        user_id=user_id,
        period_start=period_start.date(),
        period_end=period_end.date(),
        payload=payload,
    )
    if not inserted:
        return GenerationResult(user_id=user_id, inserted=False, reason="already_exists")

    # Best-effort: push + email when a fresh report lands. The unique
    # index on (user_id, period_start) guarantees we only get here on a
    # genuinely new row, so the cron can't double-notify.
    try:
        await _notify_mirror_ready(
            supabase,
            user_id=user_id,
            period_start=period_start.date(),
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "mirror.notify_failed",
            user_id=user_id,
            period_start=period_start.date().isoformat(),
            error=str(err),
        )

    return GenerationResult(user_id=user_id, inserted=True)


async def _resolve_email(
    supabase: AsyncClient, *, user_id: str
) -> str | None:
    try:
        res = await supabase.auth.admin.get_user_by_id(user_id)
    except Exception as err:  # pragma: no cover - non-fatal
        log.info("mirror.email_lookup_failed", user_id=user_id, error=str(err))
        return None
    user_obj = getattr(res, "user", None) or getattr(res, "data", None)
    email_val = getattr(user_obj, "email", None) if user_obj else None
    return email_val if isinstance(email_val, str) and email_val else None


async def _notify_mirror_ready(
    supabase: AsyncClient,
    *,
    user_id: str,
    period_start: date,
) -> None:
    """Push (mirror_ready) + email (mirror_report_ready — different name
    per the existing template registry inconsistency, kept for backwards
    compatibility).
    """

    period_iso = period_start.isoformat()
    try:
        await deliver_to_user(
            user_id=user_id,
            template="mirror_ready",
            variables={},
            deep_link=None,
            idempotency_key=f"push:mirror_ready:{user_id}:{period_iso}",
            supabase=supabase,
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "mirror.push_failed", user_id=user_id, period_start=period_iso, error=str(err)
        )

    email_addr = await _resolve_email(supabase, user_id=user_id)
    if not email_addr:
        return
    try:
        await send_email(
            template="mirror_report_ready",
            to_email=email_addr,
            variables={"week_label": period_iso},
            user_id=user_id,
            idempotency_key=f"email:mirror_report_ready:{user_id}:{period_iso}",
            supabase=supabase,
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "mirror.email_failed",
            user_id=user_id,
            period_start=period_iso,
            error=str(err),
        )


async def run_weekly(
    *,
    period_start: datetime,
    period_end: datetime | None = None,
    client: LiteLLMClient | None = None,
    supabase: AsyncClient | None = None,
) -> dict[str, int]:
    """Top-level entry point. Iterates eligible users."""

    sb = supabase or await get_supabase()
    end = period_end or period_start + timedelta(days=7)
    users = await find_eligible_users(sb, period_start=period_start, period_end=end)

    inserted = 0
    skipped = 0
    for profile in users:
        user_id = str(profile["id"])
        result = await run_for_user(
            sb,
            user_id=user_id,
            period_start=period_start,
            period_end=end,
            client=client,
        )
        if result.inserted:
            inserted += 1
        else:
            skipped += 1

    log.info(
        "mirror.batch.done",
        period_start=period_start.isoformat(),
        period_end=end.isoformat(),
        eligible_users=len(users),
        inserted=inserted,
        skipped=skipped,
    )
    return {
        "eligible_users": len(users),
        "inserted": inserted,
        "skipped": skipped,
    }


__all__ = [
    "ELIGIBLE_TIERS",
    "GenerationResult",
    "MirrorDodge",
    "MirrorPattern",
    "MirrorReportPayload",
    "fetch_window_signals",
    "find_eligible_users",
    "generate_report",
    "persist_report",
    "run_for_user",
    "run_weekly",
]
