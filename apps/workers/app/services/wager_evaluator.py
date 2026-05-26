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

from app.config import get_settings
from app.prompts.wager_evaluator import WAGER_EVALUATOR_PROMPT
from app.services import analytics
from app.services._db_typing import row_or_none, rows as _rows
from app.services.email import TemplateName as EmailTemplateName, send_email
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
            metadata=build_trace_metadata(
                name="wager_evaluator",
                user_id=str(wager.get("user_id") or "") or None,
                mode="wager_evaluator",
            ),
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


# ----- Outcome notification -------------------------------------------------


def _format_stake(cents: int | None) -> str:
    """Money format used in email + push variables. Two-decimal dollars
    with thousand separators (e.g. "$1,234.00"). Falls back to "$0.00"
    for invalid input.
    """

    if not isinstance(cents, int) or cents < 0:
        return "$0.00"
    dollars, remainder = divmod(cents, 100)
    return f"${dollars:,}.{remainder:02d}"


def _format_stake_amount_only(cents: int | None) -> str:
    """`${stake}` push body has a literal "$" already; return just the
    formatted dollar amount.
    """

    if not isinstance(cents, int) or cents < 0:
        return "0.00"
    dollars, remainder = divmod(cents, 100)
    return f"{dollars:,}.{remainder:02d}"


async def _resolve_email(
    supabase: AsyncClient, *, user_id: str
) -> str | None:
    try:
        res = await supabase.auth.admin.get_user_by_id(user_id)
    except Exception as err:  # pragma: no cover - non-fatal
        log.info(
            "wager_evaluator.email_lookup_failed", user_id=user_id, error=str(err)
        )
        return None
    user_obj = getattr(res, "user", None) or getattr(res, "data", None)
    email_val = getattr(user_obj, "email", None) if user_obj else None
    return email_val if isinstance(email_val, str) and email_val else None


async def _resolve_anti_charity_name(
    supabase: AsyncClient, *, slug: str | None
) -> str:
    if not slug:
        return "(unknown)"
    try:
        res = (
            await supabase.table("anti_charities")
            .select("name")
            .eq("slug", slug)
            .maybe_single()
            .execute()
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.info(
            "wager_evaluator.anti_charity_lookup_failed",
            slug=slug,
            error=str(err),
        )
        return slug
    row = row_or_none(res.data) if res is not None else None
    name_val = row.get("name") if row else None
    if isinstance(name_val, str) and name_val:
        return name_val
    return slug


async def _notify_outcome(
    supabase: AsyncClient,
    *,
    wager: dict[str, Any],
    outcome: Outcome,
) -> None:
    """Push + email after a verdict lands.

    - `failed`  → push wager_failed + email wager_lost
    - `succeeded` → email wager_won only (no "you won" push per §13;
                    the spec only registers a wager_failed push template)

    Idempotency is per (wager_id, outcome) — a wager only ever has one
    final outcome so retries cleanly dedupe.
    """

    wager_id = str(wager["id"])
    user_id = wager.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        return

    app_url = str(get_settings().app_url).rstrip("/")
    stake_cents = wager.get("stake_cents") if isinstance(wager.get("stake_cents"), int) else 0

    if outcome == "failed":
        anti_charity_name = await _resolve_anti_charity_name(
            supabase, slug=wager.get("anti_charity_slug")
        )
        try:
            await deliver_to_user(
                user_id=user_id,
                template="wager_failed",
                variables={
                    "stake": _format_stake_amount_only(stake_cents),
                    "anti_charity": anti_charity_name,
                },
                deep_link=f"{app_url}/wagers/{wager_id}",
                idempotency_key=f"push:wager_failed:{wager_id}",
                supabase=supabase,
            )
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning(
                "wager_evaluator.notify.push_failed",
                wager_id=wager_id,
                error=str(err),
            )

    email_addr = await _resolve_email(supabase, user_id=user_id)
    if email_addr:
        email_template: EmailTemplateName = (
            "wager_lost" if outcome == "failed" else "wager_won"
        )
        variables: dict[str, Any] = {
            "goal": wager.get("goal") or "(your goal)",
            "stake_formatted": _format_stake(stake_cents),
            "wager_id": wager_id,
        }
        if outcome == "failed":
            variables["anti_charity_name"] = await _resolve_anti_charity_name(
                supabase, slug=wager.get("anti_charity_slug")
            )
        try:
            await send_email(
                template=email_template,
                to_email=email_addr,
                variables=variables,
                user_id=user_id,
                idempotency_key=f"email:{email_template}:{wager_id}",
                supabase=supabase,
            )
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning(
                "wager_evaluator.notify.email_failed",
                wager_id=wager_id,
                error=str(err),
            )


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

    # Best-effort outcome notification — push (failed only) + email
    # (both outcomes). Failures here don't roll back the verdict.
    try:
        await _notify_outcome(supabase, wager=wager, outcome=verdict.outcome)
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "wager_evaluator.notify_failed",
            wager_id=wager_id,
            error=str(err),
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
