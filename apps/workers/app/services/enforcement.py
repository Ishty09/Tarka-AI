"""Enforcement helpers — quota + suspension (CLAUDE.md §8.3, §22).

Every workers endpoint that the user can trigger funnels through this
module so a single source of truth governs:

- 403 when `profiles.is_suspended` is true.
- 429 when the matching usage_quotas counter has been hit.

The shape of the 429 detail matches the existing `QuotaExceededResponse`
schema so the apps/web error UIs (toast, upgrade prompt) don't have to
change. The /chat/stream endpoint already wraps 429 in an SSE event;
this module exposes both an HTTPException-raising helper and a plain
QuotaState getter, so SSE callers can format the error themselves while
JSON callers can let FastAPI render it.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException, status
from supabase import AsyncClient

from app.services._db_typing import row_or_none
from app.services.quotas import (
    QuotaState,
    get_council_quota,
    get_message_quota,
    get_roast_feed_quota,
)

QuotaScope = Literal["messages", "council", "roast_feed"]


SCOPE_GETTERS = {
    "messages": get_message_quota,
    "council": get_council_quota,
    "roast_feed": get_roast_feed_quota,
}


UPGRADE_URL_DEFAULT = "/pricing"


def quota_detail(quota: QuotaState, *, scope: QuotaScope = "messages") -> dict[str, Any]:
    """Standard 429 detail payload shared across all endpoints."""

    return {
        "error": "quota_exceeded",
        "scope": scope,
        "tier": quota.tier,
        "limit": quota.limit,
        "used": quota.used,
        "reset_at": quota.reset_at.isoformat(),
        "upgrade_url": UPGRADE_URL_DEFAULT,
    }


class SuspendedUserError(HTTPException):
    """403 raised when a suspended user hits a worker endpoint."""

    def __init__(self, *, reason: str | None) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "user_suspended",
                "reason": reason or "Account suspended.",
            },
        )


async def assert_not_suspended(supabase: AsyncClient, *, user_id: str) -> None:
    """Raise SuspendedUserError if `profiles.is_suspended=true`."""

    res = (
        await supabase.table("profiles")
        .select("is_suspended, suspension_reason")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        return
    if row.get("is_suspended") is True:
        raise SuspendedUserError(reason=row.get("suspension_reason"))


async def check_quota(
    supabase: AsyncClient,
    *,
    user_id: str,
    scope: QuotaScope,
) -> QuotaState:
    """Read the named quota. Caller should branch on `.exceeded`."""

    getter = SCOPE_GETTERS[scope]
    return await getter(supabase, user_id)


async def enforce_quota(
    supabase: AsyncClient,
    *,
    user_id: str,
    scope: QuotaScope,
) -> QuotaState:
    """Read + raise 429 if exhausted. Returns the state for callers that
    want to log or include it in the success path.
    """

    quota = await check_quota(supabase, user_id=user_id, scope=scope)
    if quota.exceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=quota_detail(quota, scope=scope),
        )
    return quota


async def enforce_user(
    supabase: AsyncClient,
    *,
    user_id: str,
    scope: QuotaScope | None = None,
) -> QuotaState | None:
    """Convenience: suspension check + optional quota enforcement in
    a single call. The two checks ALWAYS run in the same order so any
    suspended user gets a 403 even if they were also out of quota.
    """

    await assert_not_suspended(supabase, user_id=user_id)
    if scope is None:
        return None
    return await enforce_quota(supabase, user_id=user_id, scope=scope)


__all__ = [
    "UPGRADE_URL_DEFAULT",
    "QuotaScope",
    "SuspendedUserError",
    "assert_not_suspended",
    "check_quota",
    "enforce_quota",
    "enforce_user",
    "quota_detail",
]
