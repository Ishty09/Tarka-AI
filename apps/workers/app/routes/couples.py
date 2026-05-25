"""POST /couples/disputes/:dispute_id/arbitrate

Called by apps/web's couples server action once both perspectives are
submitted. We re-load the row inside workers (don't trust the caller's
payload), confirm both perspectives are in, and call the arbitrator.

Per CLAUDE.md §1.4, every LLM call stays inside workers. Web is the
trust boundary that delegates here via WORKERS_INTERNAL_SECRET.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from pydantic import BaseModel

from app.config import get_settings
from app.services._db_typing import row_or_none
from app.services.dispute_arbitrator import ArbitrationError, arbitrate
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/couples", tags=["couples"])


def _verify_internal_caller(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()
    if not settings.workers_internal_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "internal_secret_unset")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer")
    if authorization.removeprefix("Bearer ").strip() != settings.workers_internal_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token")


class ArbitrateResponse(BaseModel):
    ok: bool
    status: str
    verdict: dict[str, Any] | None = None
    error: str | None = None


@router.post(
    "/disputes/{dispute_id}/arbitrate",
    response_model=ArbitrateResponse,
    dependencies=[Depends(_verify_internal_caller)],
)
async def arbitrate_dispute(
    dispute_id: str = Path(..., min_length=36, max_length=36),
) -> ArbitrateResponse:
    supabase = await get_supabase()

    row = row_or_none(
        await (
            supabase.table("couple_disputes")
            .select(
                "id, couple_link_id, status, "
                "perspective_a_text, perspective_a_user_id, perspective_a_submitted_at, "
                "perspective_b_text, perspective_b_user_id, perspective_b_submitted_at, "
                "arbitration"
            )
            .eq("id", dispute_id)
            .single()
            .execute()
        )
    )

    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dispute not found")

    if row.get("arbitration") and row["status"] == "arbitrated":
        # Idempotent: already arbitrated, return existing verdict.
        return ArbitrateResponse(
            ok=True, status="arbitrated", verdict=row["arbitration"]
        )

    a_text = row.get("perspective_a_text")
    b_text = row.get("perspective_b_text")
    if not a_text or not b_text:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "both perspectives required before arbitration",
        )

    # Stamp arbitrating state so concurrent calls bounce off the check above
    # (will return early with the verdict once one wins the race).
    await (
        supabase.table("couple_disputes")
        .update({"status": "arbitrating"})
        .eq("id", dispute_id)
        .execute()
    )

    try:
        result = await arbitrate(
            perspective_a=a_text,
            perspective_b=b_text,
            couple_link_id=row["couple_link_id"],
            user_a_id=row["perspective_a_user_id"] or "anonymous",
        )
    except ArbitrationError as err:
        log.warning(
            "dispute.arbitration_failed",
            dispute_id=dispute_id,
            error=str(err),
        )
        # Revert status so the user can retry.
        await (
            supabase.table("couple_disputes")
            .update({"status": "awaiting"})
            .eq("id", dispute_id)
            .execute()
        )
        return ArbitrateResponse(ok=False, status="awaiting", error=str(err))

    await (
        supabase.table("couple_disputes")
        .update(
            {
                "status": "arbitrated",
                "arbitration": result.verdict,
                "arbitrated_at": "now()",
                "arbitration_model": result.model,
            }
        )
        .eq("id", dispute_id)
        .execute()
    )

    log.info(
        "dispute.arbitrated",
        dispute_id=dispute_id,
        confidence=result.verdict.get("confidence"),
        who_escalated=result.verdict.get("who_escalated_first"),
    )

    return ArbitrateResponse(
        ok=True, status="arbitrated", verdict=result.verdict
    )
