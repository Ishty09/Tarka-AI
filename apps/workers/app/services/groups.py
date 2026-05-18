"""Group rooms shared-chat service (CLAUDE.md §9.3.4).

start_group_session creates or returns the single conversation bound to
a group_room. Membership is enforced via group_members; the AI joins
the same conversation as members.

§9.3.4 says "after 3 human messages, AI intervenes". We implement that
as: AFTER persisting each user message, count consecutive user-role
messages from the most recent one back. If that streak reaches the
trigger count, the chat route runs the LLM as usual. Otherwise the
route emits a "saved" SSE event and skips the LLM call.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from supabase import AsyncClient

from app.services._db_typing import row_or_none, rows as _rows

log = structlog.get_logger(__name__)


# §9.3.4: AI intervenes after this many consecutive human turns.
AI_TURN_TAKING_THRESHOLD = 3


class GroupNotFoundError(Exception):
    pass


class GroupArchivedError(Exception):
    pass


class NotAGroupMemberError(Exception):
    pass


@dataclass(slots=True)
class GroupSession:
    group_id: str
    conversation_id: str
    mediator_persona_id: str
    member_ids: list[str]


async def _load_group(supabase: AsyncClient, group_id: str) -> dict[str, object]:
    res = (
        await supabase.table("group_rooms")
        .select("id, owner_id, mediator_persona_id, archived")
        .eq("id", group_id)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        raise GroupNotFoundError(group_id)
    return row


async def _load_members(supabase: AsyncClient, group_id: str) -> list[str]:
    res = (
        await supabase.table("group_members")
        .select("user_id")
        .eq("group_id", group_id)
        .execute()
    )
    return [str(r["user_id"]) for r in _rows(res.data) if r.get("user_id")]


async def _find_existing_conversation(
    supabase: AsyncClient, *, group_id: str
) -> str | None:
    res = (
        await supabase.table("conversations")
        .select("id, archived")
        .eq("group_room_id", group_id)
        .order("created_at", desc=False)
        .limit(5)
        .execute()
    )
    for row in _rows(res.data):
        if not row.get("archived"):
            return str(row["id"])
    return None


async def start_group_session(
    supabase: AsyncClient,
    *,
    user_id: str,
    group_id: str,
) -> GroupSession:
    """Find or create the shared conversation for an active group room.

    Raises GroupNotFoundError / GroupArchivedError / NotAGroupMemberError
    so the route can return 404 / 409 / 403.
    """

    group = await _load_group(supabase, group_id)
    if group.get("archived"):
        raise GroupArchivedError(group_id)

    members = await _load_members(supabase, group_id)
    if user_id not in members:
        raise NotAGroupMemberError(user_id)

    mediator_persona_id = group.get("mediator_persona_id")
    if not isinstance(mediator_persona_id, str):
        raise RuntimeError("group_missing_mediator_persona")

    existing = await _find_existing_conversation(supabase, group_id=group_id)
    if existing is not None:
        return GroupSession(
            group_id=group_id,
            conversation_id=existing,
            mediator_persona_id=mediator_persona_id,
            member_ids=members,
        )

    # Conversation belongs to the owner as a convention; other members
    # participate via the §6.7 conversations_group_member RLS policy.
    conversation_id = str(uuid.uuid4())
    owner_id = str(group["owner_id"])
    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": owner_id,
                "persona_id": mediator_persona_id,
                "mode": "mediate",
                "group_room_id": group_id,
                "title": "Group chat",
                "metadata": {
                    "tool": "group",
                    "member_ids": members,
                },
            }
        )
        .execute()
    )
    return GroupSession(
        group_id=group_id,
        conversation_id=conversation_id,
        mediator_persona_id=mediator_persona_id,
        member_ids=members,
    )


async def count_recent_consecutive_humans(
    supabase: AsyncClient,
    *,
    conversation_id: str,
    lookback: int = 12,
) -> int:
    """Count user-role messages from the most recent message backward,
    stopping at the first non-user role.

    A higher `lookback` gives more headroom; AI_TURN_TAKING_THRESHOLD=3
    means we never need to scan more than ~12 rows. We over-scan a
    little to handle clusters of safety-refused turns or tool messages.
    """

    res = (
        await supabase.table("messages")
        .select("role, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(lookback)
        .execute()
    )
    streak = 0
    for row in _rows(res.data):
        if row.get("role") == "user":
            streak += 1
        else:
            break
    return streak


__all__ = [
    "AI_TURN_TAKING_THRESHOLD",
    "GroupArchivedError",
    "GroupNotFoundError",
    "GroupSession",
    "NotAGroupMemberError",
    "count_recent_consecutive_humans",
    "start_group_session",
]
