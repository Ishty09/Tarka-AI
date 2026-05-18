"""Tier + usage quota enforcement (§8.1, §8.3).

Reads `profiles.tier` to find the §8.1 limit, then compares against the
current row in `usage_quotas` for today. Increment is best-effort: on a
race two parallel chat turns can both pass the same check and produce a
small over-count. We tolerate that and reset daily at 00:00 UTC via a
pg_cron job (§8.3 step 6) which the §27 step 51 quota job will install.

The interface here is the python mirror of @quarrel/shared TIER_LIMITS;
both must move together.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal, cast

import structlog
from supabase import AsyncClient

from app.services._db_typing import row_or_none

log = structlog.get_logger(__name__)

Tier = Literal["free", "pro", "max"]


# §8.1 message quota per tier. Other §8.1 limits land alongside the
# features that consume them — this module owns the chat-message quota.
MESSAGES_PER_DAY: dict[Tier, int] = {
    "free": 15,
    "pro": 200,
    "max": 1500,
}


# §8.1 council runs. Spec is free=1/week, pro=3/day, max=20/day. For MVP
# we use a daily counter for every tier — free getting 1/day is slightly
# more generous than 1/week, which we accept until §27 step 51 lands the
# proper period-aware reset job. Note the variance in commit history when
# we swap.
# §8.1 roast feed posts. Spec is free=read-only, pro=5/week, max=30/week.
# We approximate weekly via a daily counter: free=0, pro=1/day (~7/week),
# max=5/day (~35/week). Period-aware reset is part of §27 step 51.
ROAST_FEED_POSTS_PER_DAY: dict[Tier, int] = {
    "free": 0,
    "pro": 1,
    "max": 5,
}


COUNCIL_RUNS_PER_DAY: dict[Tier, int] = {
    "free": 1,
    "pro": 3,
    "max": 20,
}


@dataclass(slots=True)
class QuotaState:
    tier: Tier
    used: int
    limit: int
    reset_at: datetime

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exceeded(self) -> bool:
        return self.used >= self.limit


async def get_message_quota(supabase: AsyncClient, user_id: str) -> QuotaState:
    """Read current quota state for a user. Creates today's row if missing.

    Returns the in-memory state without taking a slot — callers should
    bail on `exceeded` BEFORE calling `increment_message_count`.
    """

    today = date.today()
    # 00:00 UTC the next day; matches the cron reset window in §8.3 step 6.
    reset_at = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=UTC)

    tier = await _read_tier(supabase, user_id)
    limit = MESSAGES_PER_DAY[tier]
    used = await _read_messages_used(supabase, user_id, today)

    return QuotaState(tier=tier, used=used, limit=limit, reset_at=reset_at)


async def increment_message_count(
    supabase: AsyncClient,
    user_id: str,
    *,
    count: int = 1,
) -> None:
    """Add `count` to today's messages_used row (§9.3.3 tools like Breakup
    Analyzer charge >1 per invocation).

    Inserts the row on first write of the day (the §6.5 PK is
    (user_id, period_start)). Subsequent writes increment via a Postgres
    function added with the §27 step 51 cron — until then we read-modify-
    write, which is racy but acceptable at our launch traffic.
    """

    if count <= 0:
        return

    today = date.today()
    period_start = today.isoformat()

    existing = (
        await supabase.table("usage_quotas")
        .select("messages_used")
        .eq("user_id", user_id)
        .eq("period_start", period_start)
        .maybe_single()
        .execute()
    )
    row = row_or_none(existing.data) if existing is not None else None

    if row is None:
        await (
            supabase.table("usage_quotas")
            .insert(
                {
                    "user_id": user_id,
                    "period_start": period_start,
                    "messages_used": count,
                }
            )
            .execute()
        )
        return

    current = int(row.get("messages_used", 0) or 0)
    await (
        supabase.table("usage_quotas")
        .update({"messages_used": current + count})
        .eq("user_id", user_id)
        .eq("period_start", period_start)
        .execute()
    )


async def get_council_quota(supabase: AsyncClient, user_id: str) -> QuotaState:
    today = date.today()
    reset_at = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    tier = await _read_tier(supabase, user_id)
    limit = COUNCIL_RUNS_PER_DAY[tier]
    used = await _read_counter(supabase, user_id, today, column="council_runs_used")
    return QuotaState(tier=tier, used=used, limit=limit, reset_at=reset_at)


async def increment_council_count(supabase: AsyncClient, user_id: str) -> None:
    await _increment_counter(supabase, user_id, column="council_runs_used")


async def get_roast_feed_quota(supabase: AsyncClient, user_id: str) -> QuotaState:
    today = date.today()
    reset_at = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    tier = await _read_tier(supabase, user_id)
    limit = ROAST_FEED_POSTS_PER_DAY[tier]
    used = await _read_counter(supabase, user_id, today, column="roast_feed_posts_used")
    return QuotaState(tier=tier, used=used, limit=limit, reset_at=reset_at)


async def increment_roast_feed_count(supabase: AsyncClient, user_id: str) -> None:
    await _increment_counter(supabase, user_id, column="roast_feed_posts_used")


async def _read_counter(
    supabase: AsyncClient,
    user_id: str,
    period: date,
    *,
    column: str,
) -> int:
    res = (
        await supabase.table("usage_quotas")
        .select(column)
        .eq("user_id", user_id)
        .eq("period_start", period.isoformat())
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        return 0
    return int(row.get(column, 0) or 0)


async def _increment_counter(
    supabase: AsyncClient, user_id: str, *, column: str
) -> None:
    today = date.today()
    period_start = today.isoformat()

    existing = (
        await supabase.table("usage_quotas")
        .select(column)
        .eq("user_id", user_id)
        .eq("period_start", period_start)
        .maybe_single()
        .execute()
    )
    row = row_or_none(existing.data) if existing is not None else None

    if row is None:
        await (
            supabase.table("usage_quotas")
            .insert(
                {
                    "user_id": user_id,
                    "period_start": period_start,
                    column: 1,
                }
            )
            .execute()
        )
        return

    current = int(row.get(column, 0) or 0)
    await (
        supabase.table("usage_quotas")
        .update({column: current + 1})
        .eq("user_id", user_id)
        .eq("period_start", period_start)
        .execute()
    )


async def _read_tier(supabase: AsyncClient, user_id: str) -> Tier:
    res = (
        await supabase.table("profiles")
        .select("tier")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        log.warning("quotas.no_profile_row", user_id=user_id)
        return "free"
    tier_value = row.get("tier", "free")
    if tier_value not in MESSAGES_PER_DAY:
        log.warning("quotas.unknown_tier", user_id=user_id, tier=tier_value)
        return "free"
    return cast(Tier, tier_value)


async def _read_messages_used(supabase: AsyncClient, user_id: str, period: date) -> int:
    res = (
        await supabase.table("usage_quotas")
        .select("messages_used")
        .eq("user_id", user_id)
        .eq("period_start", period.isoformat())
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        return 0
    return int(row.get("messages_used", 0) or 0)
