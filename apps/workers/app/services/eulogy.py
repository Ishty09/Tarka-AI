"""Quarterly Eulogy Test generator (CLAUDE.md §9.4.3).

Per quarter, for each Pro/Max user with activity in the 90-day lookback,
gather facts + wagers + check-ins + streaks, send to quarrel-argue, persist
the eulogy text. Free tier is excluded per §8.1.

The schema (§6.2 eulogy_reports) uses a freeform `quarter` text column —
we format as `YYYY-Q[1-4]` so it's both sortable and matches the §9.4.3
push template's {quarter} variable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from supabase import AsyncClient

from app.prompts.eulogy import EULOGY_PROMPT
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


ELIGIBLE_TIERS = {"pro", "max"}

# Caps to keep prompt size bounded — a heavy user could have hundreds of
# facts and dozens of wagers over 90 days.
MAX_FACTS = 150
MAX_WAGERS = 50
MAX_CHECKIN_HABITS = 20

# Window the §9.4.3 prompt is documented against.
WINDOW_DAYS = 90

# Length floor we expect from the model. Anything shorter is almost
# certainly a refusal or malformed continuation; we drop and let the next
# scheduled run retry.
MIN_CONTENT_CHARS = 200
MAX_CONTENT_CHARS = 4000


@dataclass(slots=True)
class GenerationResult:
    user_id: str
    quarter: str
    inserted: bool
    reason: str | None = None


# ----- Quarter helpers -------------------------------------------------------


def quarter_slug(d: datetime) -> str:
    """Format a datetime as `YYYY-Q[1-4]` (e.g. `2026-Q2`)."""

    q = (d.month - 1) // 3 + 1
    return f"{d.year}-Q{q}"


def previous_quarter_window(now: datetime) -> tuple[str, datetime, datetime]:
    """Return (slug, period_start, period_end) for the *previous* quarter.

    The job is scheduled to fire on the first day of a new quarter; the
    eulogy is for the quarter that just ended.
    """

    # Anchor `now` to the first of its month, then back up three months.
    end = datetime(now.year, ((now.month - 1) // 3) * 3 + 1, 1, tzinfo=UTC)
    start_month_index = (end.month - 1) - 3
    start_year = end.year + (start_month_index // 12)
    start_month = (start_month_index % 12) + 1
    start = datetime(start_year, start_month, 1, tzinfo=UTC)
    # Anchor `slug` to the start month so a generation in 2026-04 produces
    # "2026-Q1".
    slug = quarter_slug(start)
    return slug, start, end


# ----- DB fetchers -----------------------------------------------------------


async def fetch_signals(
    supabase: AsyncClient,
    user_id: str,
    *,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, list[Any]]:
    """Return facts + wagers + per-wager check-in counts + streaks."""

    fact_res = (
        await supabase.table("user_facts")
        .select("fact, category")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .gte("created_at", period_start.isoformat())
        .lt("created_at", period_end.isoformat())
        .order("created_at", desc=False)
        .limit(MAX_FACTS)
        .execute()
    )
    facts = _rows(fact_res.data)

    wager_res = (
        await supabase.table("wagers")
        .select("id, goal, stake_cents, start_at, end_at, status")
        .eq("user_id", user_id)
        .gte("start_at", period_start.date().isoformat())
        .lt("start_at", period_end.date().isoformat())
        .order("start_at", desc=False)
        .limit(MAX_WAGERS)
        .execute()
    )
    wagers = _rows(wager_res.data)

    checkin_res = (
        await supabase.table("wager_checkins")
        .select("wager_id, status")
        .eq("user_id", user_id)
        .gte("checkin_date", period_start.date().isoformat())
        .lt("checkin_date", period_end.date().isoformat())
        .execute()
    )
    checkins = _rows(checkin_res.data)

    streak_res = (
        await supabase.table("streaks")
        .select("habit, current_streak, longest_streak, last_checkin_at")
        .eq("user_id", user_id)
        .limit(MAX_CHECKIN_HABITS)
        .execute()
    )
    streaks = _rows(streak_res.data)

    return {
        "facts": facts,
        "wagers": wagers,
        "checkins": checkins,
        "streaks": streaks,
    }


def _format_prompt_input(signals: dict[str, list[Any]]) -> str:
    facts_block = (
        "\n".join(f"- [{f.get('category') or '—'}] {f.get('fact')}" for f in signals["facts"])
        or "(none)"
    )

    wagers_block_lines = []
    checkin_summary: dict[str, dict[str, int]] = {}
    for c in signals["checkins"]:
        wid = str(c.get("wager_id"))
        bucket = checkin_summary.setdefault(wid, {"completed": 0, "missed": 0, "skipped": 0})
        status = str(c.get("status", "missed"))
        if status in bucket:
            bucket[status] += 1

    for w in signals["wagers"]:
        wid = str(w.get("id"))
        cs = checkin_summary.get(wid, {"completed": 0, "missed": 0, "skipped": 0})
        line = (
            f"- {w.get('goal')} | stake ${int(w.get('stake_cents') or 0) / 100:.2f} | "
            f"{w.get('start_at')}→{w.get('end_at')} | status={w.get('status')} | "
            f"check-ins completed={cs['completed']} missed={cs['missed']} skipped={cs['skipped']}"
        )
        wagers_block_lines.append(line)
    wagers_block = "\n".join(wagers_block_lines) or "(none)"

    kept_block_lines = []
    for s in signals["streaks"]:
        kept_block_lines.append(
            f"- habit: {s.get('habit')} | current={s.get('current_streak')} | "
            f"longest={s.get('longest_streak')} | last_checkin={s.get('last_checkin_at')}"
        )
    kept_block = "\n".join(kept_block_lines) or "(none)"

    return (
        "<facts>\n"
        f"{facts_block}\n"
        "</facts>\n\n"
        "<commitments_made>\n"
        f"{wagers_block}\n"
        "</commitments_made>\n\n"
        "<commitments_kept>\n"
        f"{kept_block}\n"
        "</commitments_kept>"
    )


# ----- LLM call --------------------------------------------------------------


async def generate_eulogy_text(
    *,
    signals: dict[str, list[Any]],
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> str | None:
    """One LLM call returning the eulogy prose. None on any failure."""

    if not any(signals.get(k) for k in ("facts", "wagers", "streaks")):
        return None

    llm = client or get_llm_client()
    payload = _format_prompt_input(signals)

    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": EULOGY_PROMPT},
                {"role": "user", "content": payload},
            ],
            temperature=0.6,
            user=user_id,
            metadata=build_trace_metadata(
                name="eulogy",
                user_id=user_id,
                mode="eulogy",
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("eulogy.generate.llm_error", user_id=user_id, error=str(err))
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

    content = raw.strip()
    if len(content) < MIN_CONTENT_CHARS:
        log.warning("eulogy.generate.too_short", user_id=user_id, length=len(content))
        return None
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS]
    return content


# ----- Persist + orchestration ----------------------------------------------


async def persist_eulogy(
    supabase: AsyncClient,
    *,
    user_id: str,
    quarter: str,
    content: str,
) -> bool:
    """Idempotent insert. eulogy_reports has UNIQUE(user_id, quarter)."""

    row: dict[str, Any] = {
        "user_id": user_id,
        "quarter": quarter,
        "content": content,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    try:
        res = (
            await supabase.table("eulogy_reports")
            .upsert(row, on_conflict="user_id,quarter", ignore_duplicates=True)
            .execute()
        )
    except Exception as err:  # noqa: BLE001 — best-effort
        log.warning(
            "eulogy.persist.failed",
            user_id=user_id,
            quarter=quarter,
            error=str(err),
        )
        return False
    return bool(_rows(res.data))


async def run_for_user(
    supabase: AsyncClient,
    *,
    user_id: str,
    quarter: str,
    period_start: datetime,
    period_end: datetime,
    client: LiteLLMClient | None = None,
) -> GenerationResult:
    signals = await fetch_signals(
        supabase,
        user_id,
        period_start=period_start,
        period_end=period_end,
    )
    if not signals["facts"] and not signals["wagers"] and not signals["streaks"]:
        return GenerationResult(
            user_id=user_id, quarter=quarter, inserted=False, reason="no_signal"
        )

    content = await generate_eulogy_text(
        signals=signals,
        client=client,
        user_id=user_id,
    )
    if content is None:
        return GenerationResult(
            user_id=user_id, quarter=quarter, inserted=False, reason="llm_failed"
        )

    inserted = await persist_eulogy(
        supabase,
        user_id=user_id,
        quarter=quarter,
        content=content,
    )
    if not inserted:
        return GenerationResult(
            user_id=user_id, quarter=quarter, inserted=False, reason="already_exists"
        )

    # Best-effort: notify the user the eulogy is ready. The unique index
    # on (user_id, quarter) means we only reach here when a NEW row
    # actually landed, so dedupe at the persist layer also prevents
    # double-notification on cron retries.
    try:
        await _notify_eulogy_ready(supabase, user_id=user_id, quarter=quarter)
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "eulogy.notify_failed",
            user_id=user_id,
            quarter=quarter,
            error=str(err),
        )

    return GenerationResult(user_id=user_id, quarter=quarter, inserted=True)


async def _resolve_email(
    supabase: AsyncClient, *, user_id: str
) -> str | None:
    try:
        res = await supabase.auth.admin.get_user_by_id(user_id)
    except Exception as err:  # pragma: no cover - non-fatal
        log.info("eulogy.email_lookup_failed", user_id=user_id, error=str(err))
        return None
    user_obj = getattr(res, "user", None) or getattr(res, "data", None)
    email_val = getattr(user_obj, "email", None) if user_obj else None
    return email_val if isinstance(email_val, str) and email_val else None


async def _notify_eulogy_ready(
    supabase: AsyncClient,
    *,
    user_id: str,
    quarter: str,
) -> None:
    """Push + email when a fresh eulogy lands. Per-event idempotency is
    via the (user_id, quarter) shape — eulogy_reports has UNIQUE on it
    already so we naturally never re-fire.
    """

    # Push body has no variables, but the title carries `{quarter}`.
    try:
        await deliver_to_user(
            user_id=user_id,
            template="eulogy_ready",
            variables={"quarter": quarter},
            deep_link=None,
            idempotency_key=f"push:eulogy_ready:{user_id}:{quarter}",
            supabase=supabase,
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "eulogy.push_failed", user_id=user_id, quarter=quarter, error=str(err)
        )

    email_addr = await _resolve_email(supabase, user_id=user_id)
    if not email_addr:
        return
    try:
        await send_email(
            template="eulogy_ready",
            to_email=email_addr,
            variables={"quarter": quarter},
            user_id=user_id,
            idempotency_key=f"email:eulogy_ready:{user_id}:{quarter}",
            supabase=supabase,
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "eulogy.email_failed", user_id=user_id, quarter=quarter, error=str(err)
        )


async def find_eligible_users(
    supabase: AsyncClient,
    *,
    period_start: datetime,
    period_end: datetime,
) -> list[dict[str, Any]]:
    """Pro+Max users with at least one fact, wager, or active streak in window."""

    fact_res = (
        await supabase.table("user_facts")
        .select("user_id")
        .gte("created_at", period_start.isoformat())
        .lt("created_at", period_end.isoformat())
        .execute()
    )
    wager_res = (
        await supabase.table("wagers")
        .select("user_id")
        .gte("start_at", period_start.date().isoformat())
        .lt("start_at", period_end.date().isoformat())
        .execute()
    )
    user_ids: set[str] = set()
    for row in _rows(fact_res.data):
        if row.get("user_id"):
            user_ids.add(str(row["user_id"]))
    for row in _rows(wager_res.data):
        if row.get("user_id"):
            user_ids.add(str(row["user_id"]))
    if not user_ids:
        return []

    profile_res = (
        await supabase.table("profiles")
        .select("id, tier")
        .in_("id", list(user_ids))
        .execute()
    )
    return [
        row
        for row in _rows(profile_res.data)
        if str(row.get("tier", "free")) in ELIGIBLE_TIERS
    ]


async def run_quarter(
    *,
    quarter: str,
    period_start: datetime,
    period_end: datetime,
    client: LiteLLMClient | None = None,
    supabase: AsyncClient | None = None,
) -> dict[str, int]:
    """Top-level entry point. Iterates eligible users for one quarter."""

    sb = supabase or await get_supabase()
    users = await find_eligible_users(
        sb,
        period_start=period_start,
        period_end=period_end,
    )

    inserted = 0
    skipped = 0
    for profile in users:
        user_id = str(profile["id"])
        result = await run_for_user(
            sb,
            user_id=user_id,
            quarter=quarter,
            period_start=period_start,
            period_end=period_end,
            client=client,
        )
        if result.inserted:
            inserted += 1
        else:
            skipped += 1

    log.info(
        "eulogy.batch.done",
        quarter=quarter,
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
    "MAX_CONTENT_CHARS",
    "MIN_CONTENT_CHARS",
    "WINDOW_DAYS",
    "fetch_signals",
    "find_eligible_users",
    "generate_eulogy_text",
    "persist_eulogy",
    "previous_quarter_window",
    "quarter_slug",
    "run_for_user",
    "run_quarter",
]
