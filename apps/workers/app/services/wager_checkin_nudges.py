"""Daily wager check-in nudges (§9.5.5, §13 push.wager_checkin).

For every active wager whose window covers today and which doesn't
already have a `wager_checkins` row for today, fire the wager_checkin
push. One push per active wager — if a user has multiple wagers
running, each gets its own ping because each has its own goal + stake.

Idempotency: keyed on `push:wager_checkin:<wager_id>:<today>` so a
cron retry on the same day can't double-fire.

Per-user notification prefs (push.py + notification_prefs.py) gate the
delivery — users who mute the `wagers` category never see these.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog

from app.config import get_settings
from app.services._db_typing import rows as _rows
from app.services.push import deliver_to_user
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class CheckinNudgeResult:
    eligible: int
    sent: int
    skipped: int


def _short_goal(goal: str | None, *, max_len: int = 60) -> str:
    """Truncate the goal text so push bodies don't blow their character
    budget when the user wrote a paragraph instead of a one-liner.
    """

    text = (goal or "").strip()
    if len(text) <= max_len:
        return text or "(your goal)"
    return text[: max_len - 1].rstrip() + "…"


def _format_stake(cents: int | None) -> str:
    """${stake} substitution in the push body. Whole-dollar integer; the
    template body already has the literal "$" so this returns just the
    number.
    """

    if not isinstance(cents, int) or cents <= 0:
        return "0"
    dollars = cents // 100
    return f"{dollars:,}"


async def run_nudges(
    *,
    today: date | None = None,
    supabase: Any | None = None,
) -> CheckinNudgeResult:
    """Find active wagers covering today and nudge users who haven't
    checked in yet.

    "Active" means status='active' AND start_at <= today AND end_at >= today.
    "Hasn't checked in" means no wager_checkins row exists with
    checkin_date=today for the wager.
    """

    sb = supabase or await get_supabase()
    cutoff = today or datetime.now(UTC).date()
    today_iso = cutoff.isoformat()

    res = (
        await sb.table("wagers")
        .select(
            "id, user_id, goal, stake_cents, start_at, end_at, status"
        )
        .eq("status", "active")
        .lte("start_at", today_iso)
        .gte("end_at", today_iso)
        .limit(1000)
        .execute()
    )
    active_wagers = list(_rows(res.data))

    sent = 0
    skipped = 0
    app_url = str(get_settings().app_url).rstrip("/")

    for wager in active_wagers:
        wager_id = wager.get("id")
        user_id = wager.get("user_id")
        if not isinstance(wager_id, str) or not isinstance(user_id, str):
            skipped += 1
            continue

        # Skip if a check-in already exists for today (any status).
        existing = (
            await sb.table("wager_checkins")
            .select("id")
            .eq("wager_id", wager_id)
            .eq("checkin_date", today_iso)
            .limit(1)
            .execute()
        )
        if list(_rows(existing.data)):
            skipped += 1
            continue

        deep_link = f"{app_url}/wagers/{wager_id}"
        try:
            results = await deliver_to_user(
                user_id=user_id,
                template="wager_checkin",
                variables={
                    "wager_goal": _short_goal(wager.get("goal")),
                    "stake": _format_stake(wager.get("stake_cents")),
                },
                deep_link=deep_link,
                idempotency_key=f"push:wager_checkin:{wager_id}:{today_iso}",
                supabase=sb,
            )
            if any(r.status in ("sent", "dry_run") for r in results):
                sent += 1
            else:
                # Push muted by user prefs, no subs registered, or all
                # delivery attempts failed. Count as skipped rather than
                # sent so the metric reflects actual reach.
                skipped += 1
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning(
                "wager_checkin_nudges.push_failed",
                wager_id=wager_id,
                error=str(err),
            )
            skipped += 1

    log.info(
        "wager_checkin_nudges.batch.done",
        today=today_iso,
        eligible=len(active_wagers),
        sent=sent,
        skipped=skipped,
    )
    return CheckinNudgeResult(
        eligible=len(active_wagers),
        sent=sent,
        skipped=skipped,
    )


__all__ = ["CheckinNudgeResult", "run_nudges"]
