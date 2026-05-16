"""Idempotency-key replay protection (§1.11, §6.5).

Every chat-stream request carries an idempotency_key. We look it up in
`idempotency_keys` keyed by scope + key; on hit we return the previous
response. On miss we record the request and proceed.

For streaming we can't truly "replay" the SSE — once a turn completes we
store the assistant message id under the idempotency row so a replay yields
the persisted text instead of regenerating.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from supabase import AsyncClient

from app.services._db_typing import row_or_none

log = structlog.get_logger(__name__)

# How long an idempotency record stays valid. §6.5 default is 7 days; we
# match that so the row's `expires_at` and our check agree.
IDEMPOTENCY_TTL = timedelta(days=7)


async def check_idempotency(
    supabase: AsyncClient,
    *,
    key: str,
    scope: str,
    user_id: str,
) -> dict[str, Any] | None:
    """Look up an existing idempotency record. Returns the row, or None."""

    res = (
        await supabase.table("idempotency_keys")
        .select("*")
        .eq("key", key)
        .eq("scope", scope)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        return None

    if row.get("user_id") is not None and row.get("user_id") != user_id:
        # Same key, different user — defensive log, treat as a miss.
        log.warning(
            "idempotency.user_mismatch",
            key=key,
            scope=scope,
            stored_user=row.get("user_id"),
            requesting_user=user_id,
        )
        return None
    return row


async def record_idempotency(
    supabase: AsyncClient,
    *,
    key: str,
    scope: str,
    user_id: str,
    payload_hash: str,
    response_body: dict[str, Any] | None = None,
    response_status: int | None = None,
) -> None:
    """Insert or update the idempotency row.

    Called twice during a streaming turn: once before the LLM call (with an
    empty response_body) to reserve the key, and once after persistence
    (with the final assistant_message_id payload).
    """

    expires_at = datetime.now(UTC) + IDEMPOTENCY_TTL
    await (
        supabase.table("idempotency_keys")
        .upsert(
            {
                "key": key,
                "scope": scope,
                "user_id": user_id,
                "payload_hash": payload_hash,
                "response_body": response_body,
                "response_status": response_status,
                "expires_at": expires_at.isoformat(),
            },
            on_conflict="key",
        )
        .execute()
    )
