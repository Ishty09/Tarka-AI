"""Account deletion sweeper (CLAUDE.md §12.5, §16, §27 step 58).

Two phases, run by the same cron tick:

1. **Notify** — users who have requested deletion but haven't received the
   `account_deletion_grace_started` email yet. We send the email and stamp
   `profiles.deletion_grace_notified_at` so subsequent ticks don't repeat.

2. **Sweep** — users whose `data_deletion_requested_at + 30 days <= now()`.
   We write an `audit_log` row first (the user_id link is dropped to NULL
   by the FK cascade), then call `supabase.auth.admin.delete_user`, which
   cascades through `profiles` and the rest of the user-scoped tables.

The split lets each phase fail independently. A user who never got the
email still gets their grace period because the sweep clock runs from
`data_deletion_requested_at`, not from the notification timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from supabase import AsyncClient

from app.config import get_settings
from app.services._db_typing import row_or_none
from app.services._db_typing import rows as _rows
from app.services.email import send_email
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


# Length of the recovery window. The deletion is fired when
# data_deletion_requested_at + GRACE_PERIOD <= now().
GRACE_PERIOD = timedelta(days=30)


# ----- Phase 1: notifications ------------------------------------------------


async def _list_unnotified(
    supabase: AsyncClient, *, limit: int
) -> list[dict[str, Any]]:
    """Users who requested deletion but haven't gotten the grace email."""

    res = (
        await supabase.table("profiles")
        .select(
            "id, display_name, data_deletion_requested_at, deletion_grace_notified_at"
        )
        .not_.is_("data_deletion_requested_at", "null")
        .is_("deletion_grace_notified_at", "null")
        .order("data_deletion_requested_at", desc=False)
        .limit(limit)
        .execute()
    )
    return _rows(res.data)


async def _resolve_email(
    supabase: AsyncClient, *, user_id: str
) -> str | None:
    res = await supabase.auth.admin.get_user_by_id(user_id)
    user = getattr(res, "user", None) or getattr(res, "data", None)
    email = getattr(user, "email", None) if user else None
    return email if isinstance(email, str) and email else None


async def _send_grace_email(
    supabase: AsyncClient, *, profile: dict[str, Any]
) -> bool:
    """Send the grace email + stamp `deletion_grace_notified_at`. Returns True on send."""

    user_id = str(profile["id"])
    email = await _resolve_email(supabase, user_id=user_id)
    if not email:
        log.warning("account_deletion.no_email", user_id=user_id)
        return False

    requested_at = datetime.fromisoformat(str(profile["data_deletion_requested_at"]))
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=UTC)
    delete_on = (requested_at + GRACE_PERIOD).date().isoformat()

    settings = get_settings()
    name = profile.get("display_name")
    display_name = name if isinstance(name, str) else None

    await send_email(
        template="account_deletion_grace_started",
        to_email=email,
        to_name=display_name,
        variables={"delete_on": delete_on, "app_url": str(settings.app_url)},
        idempotency_key=f"email:account_deletion_grace_started:{user_id}",
        user_id=user_id,
        supabase=supabase,
    )
    await (
        supabase.table("profiles")
        .update({"deletion_grace_notified_at": datetime.now(UTC).isoformat()})
        .eq("id", user_id)
        .execute()
    )
    return True


async def send_pending_grace_notifications(
    *, limit: int = 100, supabase: AsyncClient | None = None
) -> dict[str, int]:
    sb = supabase or await get_supabase()
    candidates = await _list_unnotified(sb, limit=limit)
    notified = 0
    failed = 0
    for profile in candidates:
        try:
            if await _send_grace_email(sb, profile=profile):
                notified += 1
        except Exception as err:
            log.warning(
                "account_deletion.notification_failed",
                user_id=profile.get("id"),
                error=str(err),
            )
            failed += 1
    return {"notified": notified, "failed": failed}


# ----- Phase 2: hard-delete sweep -------------------------------------------


@dataclass(slots=True)
class DeletionResult:
    user_id: str
    deleted: bool
    error: str | None = None


async def _list_due_for_deletion(
    supabase: AsyncClient, *, now: datetime, limit: int
) -> list[dict[str, Any]]:
    cutoff = (now - GRACE_PERIOD).isoformat()
    res = (
        await supabase.table("profiles")
        .select("id, username, data_deletion_requested_at")
        .not_.is_("data_deletion_requested_at", "null")
        .lte("data_deletion_requested_at", cutoff)
        .order("data_deletion_requested_at", desc=False)
        .limit(limit)
        .execute()
    )
    return _rows(res.data)


async def _audit_deletion(
    supabase: AsyncClient,
    *,
    user_id: str,
    requested_at: str,
) -> None:
    await (
        supabase.table("audit_log")
        .insert(
            {
                "actor_user_id": user_id,
                "action": "account_hard_deleted",
                "entity_type": "profile",
                "entity_id": user_id,
                "metadata": {
                    "data_deletion_requested_at": requested_at,
                    "executed_at": datetime.now(UTC).isoformat(),
                    "grace_period_days": GRACE_PERIOD.days,
                },
            }
        )
        .execute()
    )


async def _hard_delete_user(supabase: AsyncClient, *, user_id: str) -> None:
    """Call Supabase auth admin to nuke the user.

    auth.users → profiles is `on delete cascade`, and profiles → every
    user-scoped table is also `on delete cascade`, so this one call wipes
    the data. The audit_log entry survives because we flipped the FK to
    `on delete set null` in the companion migration.
    """

    await supabase.auth.admin.delete_user(user_id)


async def _delete_one(
    supabase: AsyncClient, *, profile: dict[str, Any]
) -> DeletionResult:
    user_id = str(profile["id"])
    requested_at = str(profile["data_deletion_requested_at"])
    try:
        await _audit_deletion(supabase, user_id=user_id, requested_at=requested_at)
        await _hard_delete_user(supabase, user_id=user_id)
    except Exception as err:
        log.warning(
            "account_deletion.hard_delete_failed",
            user_id=user_id,
            error=str(err),
        )
        return DeletionResult(user_id=user_id, deleted=False, error=str(err))
    log.info("account_deletion.hard_deleted", user_id=user_id)
    return DeletionResult(user_id=user_id, deleted=True)


async def sweep_due_deletions(
    *,
    now: datetime | None = None,
    limit: int = 50,
    supabase: AsyncClient | None = None,
) -> dict[str, int]:
    sb = supabase or await get_supabase()
    when = now or datetime.now(UTC)
    due = await _list_due_for_deletion(sb, now=when, limit=limit)
    deleted = 0
    failed = 0
    for profile in due:
        result = await _delete_one(sb, profile=profile)
        if result.deleted:
            deleted += 1
        else:
            failed += 1
    return {"candidates": len(due), "deleted": deleted, "failed": failed}


# ----- Combined driver ------------------------------------------------------


async def run_once(
    *,
    now: datetime | None = None,
    notify_limit: int = 100,
    delete_limit: int = 50,
    supabase: AsyncClient | None = None,
) -> dict[str, int]:
    """Run both phases. The cron route fires this every tick."""

    sb = supabase or await get_supabase()
    notify = await send_pending_grace_notifications(limit=notify_limit, supabase=sb)
    sweep = await sweep_due_deletions(now=now, limit=delete_limit, supabase=sb)
    return {
        "notified": notify["notified"],
        "notify_failed": notify["failed"],
        "candidates": sweep["candidates"],
        "deleted": sweep["deleted"],
        "delete_failed": sweep["failed"],
    }


# Re-exported so tests can mock alongside the rest of the service surface.
__all__ = [
    "GRACE_PERIOD",
    "DeletionResult",
    "_resolve_email",
    "run_once",
    "send_pending_grace_notifications",
    "sweep_due_deletions",
]


# row_or_none is re-exported for tests that mock at the boundary.
_ = row_or_none
