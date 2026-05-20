"""Webhook endpoints (CLAUDE.md §3, §22).

This module hosts inbound webhooks from third parties. Each handler:
1. Verifies the request signature against the provider's shared secret.
2. Looks up the event id in `idempotency_keys` to short-circuit retries.
3. Dispatches to a service-layer function that does the actual work.
4. Records the event id so the next retry is a no-op.

Webhooks are public endpoints; the signature IS the auth boundary. We do
NOT require WORKERS_INTERNAL_SECRET here — Polar can't carry that header.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.services.polar_webhooks import (
    InvalidSignatureError,
    handle_event,
    is_seen,
    mark_seen,
    parse_event,
    verify_signature,
)
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/polar")
async def polar_webhook(
    request: Request,
    webhook_id: Annotated[str | None, Header(alias="webhook-id")] = None,
    webhook_timestamp: Annotated[str | None, Header(alias="webhook-timestamp")] = None,
    webhook_signature: Annotated[str | None, Header(alias="webhook-signature")] = None,
) -> dict[str, str]:
    body = await request.body()

    try:
        verify_signature(
            body=body,
            webhook_id=webhook_id or "",
            webhook_timestamp=webhook_timestamp or "",
            signature_header=webhook_signature or "",
        )
    except InvalidSignatureError as err:
        log.warning("polar.webhook.invalid_signature", reason=str(err))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_signature") from err

    supabase = await get_supabase()
    event_id = (webhook_id or "").strip()
    if not event_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing_event_id")

    if await is_seen(supabase, event_id=event_id):
        log.info("polar.webhook.idempotent_skip", event_id=event_id)
        return {"status": "skipped"}

    try:
        event = parse_event(body)
    except (ValueError, UnicodeDecodeError) as err:
        log.warning("polar.webhook.parse_failed", error=str(err))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "parse_failed") from err

    outcome = await handle_event(supabase, event)
    await mark_seen(supabase, event_id=event_id, event_type=event.type)
    log.info(
        "polar.webhook.handled",
        event_id=event_id,
        event_type=event.type,
        outcome=outcome.status,
        reason=outcome.reason,
    )
    return {"status": outcome.status, "event_type": event.type}
