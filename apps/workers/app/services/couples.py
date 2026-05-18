"""Couples shared-conversation service (CLAUDE.md §9.3.1).

start_session creates (or returns) the single conversation bound to a
couple_links row. Both partners write into the same row; the chat route's
ownership check is relaxed for any conversation with couple_link_id set
(see routes/chat.py).

§9.3.1 says the persona overlay should be "mediator-specific, more
empathetic but still anti-sycophant". We use `the_therapist` from the
§10.1 seed since it carries the right voice — relationship lens, listens
first. The anti-sycophant base layers on top via the normal _build_system_blocks
path, so the therapist still pushes back.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from supabase import AsyncClient

from app.services._db_typing import row_or_none, rows as _rows

log = structlog.get_logger(__name__)


MEDIATOR_PERSONA_SLUG = "the_therapist"


class CoupleLinkNotActiveError(Exception):
    """Link exists but is pending / revoked / expired."""


class NotALinkMemberError(Exception):
    """Caller is neither user_a nor user_b of the link."""


class CoupleLinkNotFoundError(Exception):
    pass


@dataclass(slots=True)
class CoupleSession:
    link_id: str
    conversation_id: str
    user_a: str
    user_b: str


async def _load_link(supabase: AsyncClient, link_id: str) -> dict[str, str | None]:
    res = (
        await supabase.table("couple_links")
        .select("id, user_a, user_b, status")
        .eq("id", link_id)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        raise CoupleLinkNotFoundError(link_id)
    return row


async def _find_existing_conversation(
    supabase: AsyncClient,
    *,
    link_id: str,
) -> str | None:
    res = (
        await supabase.table("conversations")
        .select("id, archived")
        .eq("couple_link_id", link_id)
        .order("created_at", desc=False)
        .limit(5)
        .execute()
    )
    rows = _rows(res.data)
    for row in rows:
        if not row.get("archived"):
            return str(row["id"])
    return None


async def _load_mediator_persona_id(supabase: AsyncClient) -> str:
    res = (
        await supabase.table("personas")
        .select("id")
        .eq("slug", MEDIATOR_PERSONA_SLUG)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row and row.get("id"):
        return str(row["id"])
    # Defensive fallback — should never trigger in a seeded environment.
    fallback = await supabase.table("personas").select("id").limit(1).execute()
    fallback_rows = _rows(fallback.data)
    if not fallback_rows:
        raise RuntimeError("no_persona_rows_for_couples_host")
    return str(fallback_rows[0]["id"])


async def start_couple_session(
    supabase: AsyncClient,
    *,
    user_id: str,
    link_id: str,
) -> CoupleSession:
    """Find or create the shared conversation for this couple link.

    Auth: caller must be user_a or user_b. Link must be status='active'.
    Raises CoupleLinkNotFoundError / NotALinkMemberError /
    CoupleLinkNotActiveError so the route can return 404 / 403 / 409.
    """

    link = await _load_link(supabase, link_id)
    if user_id not in (link.get("user_a"), link.get("user_b")):
        raise NotALinkMemberError(user_id)
    if link.get("status") != "active":
        raise CoupleLinkNotActiveError(str(link.get("status")))

    existing = await _find_existing_conversation(supabase, link_id=link_id)
    if existing is not None:
        return CoupleSession(
            link_id=link_id,
            conversation_id=existing,
            user_a=str(link["user_a"]),
            user_b=str(link["user_b"]),
        )

    # Conversation belongs to user_a as a convention; user_b participates via
    # the conversations_couple_member RLS policy. Mode='mediate' so future
    # tooling (analytics, retention) can pivot on it.
    conversation_id = str(uuid.uuid4())
    host_persona = await _load_mediator_persona_id(supabase)
    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": link["user_a"],
                "persona_id": host_persona,
                "mode": "mediate",
                "couple_link_id": link_id,
                "title": "Couples chat",
                "metadata": {
                    "tool": "couples",
                    "persona_slug": MEDIATOR_PERSONA_SLUG,
                },
            }
        )
        .execute()
    )

    return CoupleSession(
        link_id=link_id,
        conversation_id=conversation_id,
        user_a=str(link["user_a"]),
        user_b=str(link["user_b"]),
    )


__all__ = [
    "CoupleLinkNotActiveError",
    "CoupleLinkNotFoundError",
    "CoupleSession",
    "MEDIATOR_PERSONA_SLUG",
    "NotALinkMemberError",
    "start_couple_session",
]
