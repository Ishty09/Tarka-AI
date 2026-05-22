"""Beta invite drain job (CLAUDE.md §27 step 72)."""

from __future__ import annotations

from app.services.beta_invites import send_pending_invites

DEFAULT_BATCH_LIMIT = 25


async def run_now(*, limit: int = DEFAULT_BATCH_LIMIT) -> dict[str, int]:
    return await send_pending_invites(limit=limit)
