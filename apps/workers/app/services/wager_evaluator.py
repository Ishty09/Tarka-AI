"""Wager evaluator cron (CLAUDE.md §9.5.5).

For every active wager whose end_at has passed (default: yesterday or
earlier), aggregate check-ins and ask the LLM to decide succeeded vs
failed. Persist the outcome with evaluation_notes and stamp
evaluated_at.

Disbursement (release vs capture-and-donate) is gated behind the
Polar integration which lives in §27 step 47-48. Until that flag flips
we just flip the row's status — no money moves. The audit row in
evaluation_notes makes the dry run still meaningful for the user.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient

from app.prompts.wager_evaluator import WAGER_EVALUATOR_PROMPT
from app.services import analytics
from app.services._db_typing import rows as _rows
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


Outcome = Literal["succeeded", "failed"]


class EvaluatorVerdict(BaseModel):
    outcome: Outcome
    reasoning: str = Field(min_length=10, max_length=1000)


@dataclass(slots=True)
class WagerEvaluation:
    wager_id: str
    outcome: Outcome
    reasoning: str
    capture_applied: bool  # True when Polar would capture the stake


def polar_enabled() -> bool:
    return os.environ.get("ENABLE_POLAR") == "true"


# ----- Aggregation ----------------------------------------------------------


def _aggregate(checkins: list[dict[str, Any]], total_days: int) -> dict[str, int]:
    counts = {"completed": 0, "missed": 0, "skipped": 0}
    for c in checkins:
        s = c.get("status")
        if s in counts:
            counts[s] += 1
    unfilled = max(0, total_days - sum(counts.values()))
    return {**counts, "unfilled": unfilled, "total_days": total_days}


def _format_payload(
    wager: dict[str, Any],
    checkins: list[dict[str, Any]],
    aggregate: dict[str, int],
) -> str:
    lines = [
        "<wager>",
        f"  goal: {wager.get('goal')}",
        f"  start_at: {wager.get('start_at')}",
        f"  end_at: {wager.get('end_at')}",
        "</wager>",
        "<checkins>",
    ]
    if not checkins:
        lines.append("  (no check-ins on file)")
    else:
        for i, c in enumerate(checkins, start=1):
            note = c.get("notes") or ""
            proof = c.get("proof_url") or ""
            extras = []
            if note:
                extras.append(f"note=\"{note}\"")
            if proof:
                extras.append(f"proof={proof}")
            extra_str = " " + " ".join(extras) if extras else ""
            lines.append(f"  {i}. {c.get('checkin_date')} {c.get('status')}{extra_str}")
    lines.append("</checkins>")
    lines.append("<aggregate>")
    for k in ("total_days", "completed", "missed", "skipped", "unfilled"):
        lines.append(f"  {k}: {aggregate.get(k, 0)}")
    lines.append("</aggregate>")
    return "\n".join(lines)


# ----- LLM call -------------------------------------------------------------


async def generate_verdict(
    *,
    wager: dict[str, Any],
    checkins: list[dict[str, Any]],
    aggregate: dict[str, int],
    client: LiteLLMClient | None = None,
) -> EvaluatorVerdict | None:
    llm = client or get_llm_client()
    payload = _format_payload(wager, checkins, aggregate)

    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": WAGER_EVALUATOR_PROMPT},
                {"role": "user", "content": payload},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
            user=str(wager.get("user_id") or ""),
            metadata={
                "generation_name": "wager_evaluator",
                "trace_user_id": str(wager.get("user_id") or ""),
                "tags": ["wager_evaluator"],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("wager_evaluator.llm_error", wager_id=wager.get("id"), error=str(err))
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
        log.warning("wager_evaluator.json_decode_failed", wager_id=wager.get("id"))
        return None
    try:
        return EvaluatorVerdict.model_validate(parsed)
    except ValidationError as err:
        log.warning("wager_evaluator.schema_invalid", error=str(err))
        return None


# ----- DB helpers -----------------------------------------------------------


async def find_due_wagers(
    supabase: AsyncClient,
    *,
    cutoff_date: date,
) -> list[dict[str, Any]]:
    """Active wagers with end_at <= cutoff_date. Stops at 200 per run."""

    res = (
        await supabase.table("wagers")
        .select(
            "id, user_id, goal, stake_cents, currency, anti_charity_slug, "
            "start_at, end_at, status, referee_id"
        )
        .eq("status", "active")
        .lte("end_at", cutoff_date.isoformat())
        .order("end_at", desc=False)
        .limit(200)
        .execute()
    )
    return _rows(res.data)


async def load_checkins(
    supabase: AsyncClient,
    *,
    wager_id: str,
) -> list[dict[str, Any]]:
    res = (
        await supabase.table("wager_checkins")
        .select("checkin_date, status, notes, proof_url")
        .eq("wager_id", wager_id)
        .order("checkin_date", desc=False)
        .limit(400)
        .execute()
    )
    return _rows(res.data)


async def persist_verdict(
    supabase: AsyncClient,
    *,
    wager_id: str,
    outcome: Outcome,
    reasoning: str,
) -> bool:
    payload = {
        "status": outcome,
        "evaluation_notes": reasoning,
        "evaluated_at": datetime.now(UTC).isoformat(),
    }
    try:
        await (
            supabase.table("wagers")
            .update(payload)
            .eq("id", wager_id)
            .eq("status", "active")  # guards against a parallel eval
            .execute()
        )
    except Exception as err:
        log.warning("wager_evaluator.persist_failed", wager_id=wager_id, error=str(err))
        return False
    return True


# ----- Polar disbursement stub ---------------------------------------------


async def disburse(
    *,
    wager: dict[str, Any],
    outcome: Outcome,
) -> bool:
    """Returns True if Polar would have moved money (real or simulated).

    Real Polar calls land with §27 step 47-48. For now we log the
    intended action and rely on the row status as the source of truth.
    """

    if not polar_enabled():
        log.info(
            "wager_evaluator.disburse.stubbed",
            wager_id=wager.get("id"),
            outcome=outcome,
            stake_cents=wager.get("stake_cents"),
            anti_charity=wager.get("anti_charity_slug"),
        )
        # When the flag is off, we never captured the stake in the first
        # place. Report capture_applied=False so the verdict record is
        # honest about the dry-run.
        return False

    # TODO §27 step 47-48 — call Polar:
    #   outcome='succeeded' → release the authorization (Polar refund)
    #   outcome='failed'    → capture the authorization, then transfer to
    #                         the anti-charity payout account.
    log.warning(
        "wager_evaluator.disburse.unimplemented",
        wager_id=wager.get("id"),
        outcome=outcome,
    )
    return False


# ----- Orchestration --------------------------------------------------------


async def evaluate_wager(
    supabase: AsyncClient,
    *,
    wager: dict[str, Any],
    client: LiteLLMClient | None = None,
) -> WagerEvaluation | None:
    """Evaluate one wager. Referees are out of scope for this step — if a
    referee is assigned we leave the wager 'active' so the human can
    confirm via a future surface (push notification to the referee, then
    a manual action). For MVP without a referee path we just log-skip.
    """

    wager_id = str(wager["id"])

    if wager.get("referee_id"):
        log.info(
            "wager_evaluator.referee_skip",
            wager_id=wager_id,
            referee_id=wager.get("referee_id"),
        )
        return None

    checkins = await load_checkins(supabase, wager_id=wager_id)

    # total_days is inclusive of start and end dates.
    try:
        start = date.fromisoformat(str(wager.get("start_at")))
        end = date.fromisoformat(str(wager.get("end_at")))
    except ValueError:
        log.warning("wager_evaluator.bad_dates", wager_id=wager_id)
        return None
    total_days = max(1, (end - start).days + 1)

    aggregate = _aggregate(checkins, total_days)

    verdict = await generate_verdict(
        wager=wager,
        checkins=checkins,
        aggregate=aggregate,
        client=client,
    )
    if verdict is None:
        return None

    persisted = await persist_verdict(
        supabase,
        wager_id=wager_id,
        outcome=verdict.outcome,
        reasoning=verdict.reasoning,
    )
    if not persisted:
        return None

    capture_applied = await disburse(wager=wager, outcome=verdict.outcome)

    event_name = (
        "wager_succeeded" if verdict.outcome == "succeeded" else "wager_failed"
    )
    await analytics.track_server(
        event_name,
        user_id=str(wager.get("user_id") or ""),
        data={
            "wager_id": wager_id,
            "stake_cents": wager.get("stake_cents"),
            "capture_applied": capture_applied,
        },
    )

    return WagerEvaluation(
        wager_id=wager_id,
        outcome=verdict.outcome,
        reasoning=verdict.reasoning,
        capture_applied=capture_applied,
    )


async def run_due_evaluations(
    *,
    cutoff_date: date | None = None,
    client: LiteLLMClient | None = None,
    supabase: AsyncClient | None = None,
) -> dict[str, int]:
    sb = supabase or await get_supabase()
    cutoff = cutoff_date or (datetime.now(UTC).date() - timedelta(days=0))
    candidates = await find_due_wagers(sb, cutoff_date=cutoff)

    succeeded = 0
    failed = 0
    skipped = 0
    for wager in candidates:
        result = await evaluate_wager(sb, wager=wager, client=client)
        if result is None:
            skipped += 1
        elif result.outcome == "succeeded":
            succeeded += 1
        else:
            failed += 1

    log.info(
        "wager_evaluator.batch.done",
        cutoff=cutoff.isoformat(),
        candidates=len(candidates),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
    )
    return {
        "candidates": len(candidates),
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
    }


__all__ = [
    "EvaluatorVerdict",
    "Outcome",
    "WagerEvaluation",
    "disburse",
    "evaluate_wager",
    "find_due_wagers",
    "generate_verdict",
    "load_checkins",
    "persist_verdict",
    "polar_enabled",
    "run_due_evaluations",
]
