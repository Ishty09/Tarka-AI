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


async def increment_message_count(supabase: AsyncClient, user_id: str) -> None:
    """Add one to today's messages_used row.

    Inserts the row on first write of the day (the §6.5 PK is
    (user_id, period_start)). Subsequent writes increment via a Postgres
    function added with the §27 step 51 cron — until then we read-modify-
    write, which is racy but acceptable at our launch traffic.
    """

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
                    "messages_used": 1,
                }
            )
            .execute()
        )
        return

    current = int(row.get("messages_used", 0) or 0)
    await (
        supabase.table("usage_quotas")
        .update({"messages_used": current + 1})
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
