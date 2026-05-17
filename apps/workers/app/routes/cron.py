"""Cron-triggered HTTP entry points.

Hit by an external scheduler (pg_cron edge function, GitHub Actions cron,
Trigger.dev, etc.) which signs each request with CRON_SECRET. No public
exposure — these run inside the Coolify network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.config import get_settings
from app.jobs.contradiction_batch import DEFAULT_LOOKBACK, run_nightly
from app.services.contradictions import run_batch

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/cron", tags=["cron"])


def _verify_cron_secret(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()
    if not settings.cron_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "cron_secret_unset")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer")
    if authorization.removeprefix("Bearer ").strip() != settings.cron_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token")


class ContradictionBatchRequest(BaseModel):
    """Optional override of the lookback window in hours.

    Default (none) → DEFAULT_LOOKBACK from jobs/contradiction_batch.
    Useful for manual backfill: an admin can POST {"lookback_hours": 720}
    to rerun the last 30 days of new facts.
    """

    lookback_hours: int | None = None


class ContradictionBatchResponse(BaseModel):
    since: datetime
    users: int
    pairs_judged: int
    contradictions_inserted: int


@router.post(
    "/contradiction-batch",
    response_model=ContradictionBatchResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def contradiction_batch(req: ContradictionBatchRequest) -> ContradictionBatchResponse:
    if req.lookback_hours is None:
        result = await run_nightly()
        since = datetime.now(UTC) - DEFAULT_LOOKBACK
    else:
        since = datetime.now(UTC) - timedelta(hours=req.lookback_hours)
        result = await run_batch(since=since)

    return ContradictionBatchResponse(
        since=since,
        users=result.get("users", 0),
        pairs_judged=result.get("pairs_judged", 0),
        contradictions_inserted=result.get("contradictions_inserted", 0),
    )
