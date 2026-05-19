"""Admin actions (CLAUDE.md §4, §6.7).

Every endpoint in apps/workers/app/routes/admin.py funnels through
`require_admin()` first — a single profiles.is_admin check against the
incoming X-User-Id. After that, the underlying mutation runs with the
service-role client (workers' default supabase client) so we can bypass
RLS on tables that don't carry an admin policy yet (personas,
roast_feed_posts). Every action also writes an `audit_log` row so we
have an immutable trail of who approved/suspended what.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import structlog
from supabase import AsyncClient

from app.services._db_typing import row_or_none
from app.services._db_typing import rows as _rows

log = structlog.get_logger(__name__)


class NotAdminError(PermissionError):
    """Raised when the caller's profile lacks is_admin=true."""


@dataclass(slots=True, frozen=True)
class ActorContext:
    user_id: str


async def require_admin(supabase: AsyncClient, *, user_id: str) -> ActorContext:
    """Read the actor's profile and assert is_admin=true."""

    res = (
        await supabase.table("profiles")
        .select("id, is_admin")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if not row or row.get("is_admin") is not True:
        raise NotAdminError(user_id)
    return ActorContext(user_id=user_id)


async def _audit(
    supabase: AsyncClient,
    *,
    actor: ActorContext,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    await (
        supabase.table("audit_log")
        .insert(
            {
                "actor_user_id": actor.user_id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "metadata": metadata or {},
            }
        )
        .execute()
    )


# ----- Listing reads -------------------------------------------------------


@dataclass(slots=True, frozen=True)
class PersonaPending:
    id: str
    slug: str
    name: str
    owner_id: str | None
    category: str
    visibility: str
    moderation_status: str
    system_prompt: str
    created_at: str


@dataclass(slots=True, frozen=True)
class FeedPostPending:
    id: str
    user_id: str
    conversation_id: str
    message_id: int
    caption: str | None
    moderation_status: str
    visibility: str
    created_at: str


@dataclass(slots=True, frozen=True)
class SafetyIncident:
    id: int
    user_id: str | None
    conversation_id: str | None
    message_id: int | None
    category: str
    verdict: str
    action_taken: str
    reviewed_by: str | None
    reviewed_at: str | None
    created_at: str


@dataclass(slots=True, frozen=True)
class UserSummary:
    id: str
    username: str
    display_name: str | None
    tier: str
    is_admin: bool
    is_suspended: bool
    suspension_reason: str | None
    created_at: str
    data_deletion_requested_at: str | None


async def list_pending_personas(
    supabase: AsyncClient, *, limit: int = 50
) -> list[PersonaPending]:
    res = (
        await supabase.table("personas")
        .select(
            "id, slug, name, owner_id, category, visibility, "
            "moderation_status, system_prompt, created_at",
        )
        .in_("moderation_status", ["pending", "flagged"])
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return [PersonaPending(**row) for row in _rows(res.data)]


async def list_pending_feed_posts(
    supabase: AsyncClient, *, limit: int = 50
) -> list[FeedPostPending]:
    res = (
        await supabase.table("roast_feed_posts")
        .select(
            "id, user_id, conversation_id, message_id, caption, "
            "moderation_status, visibility, created_at",
        )
        .in_("moderation_status", ["pending", "flagged"])
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return [FeedPostPending(**row) for row in _rows(res.data)]


async def list_incidents(
    supabase: AsyncClient,
    *,
    category: str | None = None,
    unreviewed_only: bool = True,
    limit: int = 100,
) -> list[SafetyIncident]:
    q = (
        supabase.table("safety_incidents")
        .select(
            "id, user_id, conversation_id, message_id, category, verdict, action_taken, "
            "reviewed_by, reviewed_at, created_at",
        )
        .order("created_at", desc=True)
        .limit(limit)
    )
    if category:
        q = q.eq("category", category)
    if unreviewed_only:
        q = q.is_("reviewed_at", "null")
    res = await q.execute()
    return [SafetyIncident(**row) for row in _rows(res.data)]


async def search_users(
    supabase: AsyncClient, *, query: str | None, limit: int = 50
) -> list[UserSummary]:
    q = (
        supabase.table("profiles")
        .select(
            "id, username, display_name, tier, is_admin, is_suspended, "
            "suspension_reason, created_at, data_deletion_requested_at",
        )
        .order("created_at", desc=True)
        .limit(limit)
    )
    if query:
        # Postgres ilike, case-insensitive substring on username or display name.
        wildcard = f"%{query.strip().lower()}%"
        q = q.or_(f"username.ilike.{wildcard},display_name.ilike.{wildcard}")
    res = await q.execute()
    return [UserSummary(**row) for row in _rows(res.data)]


# ----- Mutations -----------------------------------------------------------


PersonaAction = Literal["approve", "reject", "flag"]
FeedPostAction = Literal["approve", "reject", "remove"]


async def moderate_persona(
    supabase: AsyncClient,
    *,
    actor: ActorContext,
    persona_id: str,
    action: PersonaAction,
    notes: str | None = None,
) -> None:
    status_map: dict[PersonaAction, str] = {
        "approve": "approved",
        "reject": "rejected",
        "flag": "flagged",
    }
    new_status = status_map[action]
    await (
        supabase.table("personas")
        .update(
            {
                "moderation_status": new_status,
                "moderation_notes": notes,
                "is_safe": new_status == "approved",
            }
        )
        .eq("id", persona_id)
        .execute()
    )
    await _audit(
        supabase,
        actor=actor,
        action=f"persona_{action}",
        entity_type="persona",
        entity_id=persona_id,
        metadata={"notes": notes} if notes else None,
    )


async def moderate_feed_post(
    supabase: AsyncClient,
    *,
    actor: ActorContext,
    post_id: str,
    action: FeedPostAction,
    notes: str | None = None,
) -> None:
    if action == "approve":
        update: dict[str, Any] = {
            "moderation_status": "approved",
            "is_safe": True,
            "visibility": "public",
        }
    elif action == "reject":
        update = {
            "moderation_status": "rejected",
            "is_safe": False,
            "visibility": "removed",
        }
    else:  # remove (post was approved earlier, taking it down)
        update = {
            "moderation_status": "flagged",
            "is_safe": False,
            "visibility": "removed",
        }
    await supabase.table("roast_feed_posts").update(update).eq("id", post_id).execute()
    await _audit(
        supabase,
        actor=actor,
        action=f"feed_post_{action}",
        entity_type="roast_feed_post",
        entity_id=post_id,
        metadata={"notes": notes} if notes else None,
    )


async def suspend_user(
    supabase: AsyncClient,
    *,
    actor: ActorContext,
    user_id: str,
    reason: str,
) -> None:
    if user_id == actor.user_id:
        raise PermissionError("admin_cannot_suspend_self")
    await (
        supabase.table("profiles")
        .update({"is_suspended": True, "suspension_reason": reason})
        .eq("id", user_id)
        .execute()
    )
    await _audit(
        supabase,
        actor=actor,
        action="user_suspended",
        entity_type="profile",
        entity_id=user_id,
        metadata={"reason": reason},
    )


async def unsuspend_user(
    supabase: AsyncClient,
    *,
    actor: ActorContext,
    user_id: str,
) -> None:
    await (
        supabase.table("profiles")
        .update({"is_suspended": False, "suspension_reason": None})
        .eq("id", user_id)
        .execute()
    )
    await _audit(
        supabase,
        actor=actor,
        action="user_unsuspended",
        entity_type="profile",
        entity_id=user_id,
    )


async def review_incident(
    supabase: AsyncClient,
    *,
    actor: ActorContext,
    incident_id: int,
    notes: str | None = None,
) -> None:
    from datetime import UTC, datetime

    await (
        supabase.table("safety_incidents")
        .update(
            {
                "reviewed_by": actor.user_id,
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
        )
        .eq("id", incident_id)
        .execute()
    )
    await _audit(
        supabase,
        actor=actor,
        action="incident_reviewed",
        entity_type="safety_incident",
        entity_id=str(incident_id),
        metadata={"notes": notes} if notes else None,
    )


__all__ = [
    "ActorContext",
    "FeedPostAction",
    "FeedPostPending",
    "NotAdminError",
    "PersonaAction",
    "PersonaPending",
    "SafetyIncident",
    "UserSummary",
    "list_incidents",
    "list_pending_feed_posts",
    "list_pending_personas",
    "moderate_feed_post",
    "moderate_persona",
    "require_admin",
    "review_incident",
    "search_users",
    "suspend_user",
    "unsuspend_user",
]
