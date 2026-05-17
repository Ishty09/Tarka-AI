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
from app.jobs.eulogy_generator import run_previous_quarter
from app.jobs.mirror_mode_generator import WINDOW_DAYS, run_weekly_window
from app.services.contradictions import run_batch
from app.services.eulogy import previous_quarter_window, run_quarter
from app.services.mirror import run_weekly as run_mirror_window

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


class MirrorBatchRequest(BaseModel):
    """Optional override of the report window in days.

    Default (none) → trailing WINDOW_DAYS ending now.
    Backfill case: POST {"window_days": 30, "ending": "2026-05-17T00:00:00Z"}
    runs a single 30-day window ending at the given instant. We only support
    one window per request — schedulers iterate.
    """

    window_days: int | None = None
    ending: datetime | None = None


class MirrorBatchResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    eligible_users: int
    inserted: int
    skipped: int


@router.post(
    "/mirror-mode",
    response_model=MirrorBatchResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def mirror_mode(req: MirrorBatchRequest) -> MirrorBatchResponse:
    if req.window_days is None and req.ending is None:
        result = await run_weekly_window()
        end = datetime.now(UTC)
        start = end - timedelta(days=WINDOW_DAYS)
    else:
        end = req.ending or datetime.now(UTC)
        days = req.window_days or WINDOW_DAYS
        start = end - timedelta(days=days)
        result = await run_mirror_window(period_start=start, period_end=end)

    return MirrorBatchResponse(
        period_start=start,
        period_end=end,
        eligible_users=result.get("eligible_users", 0),
        inserted=result.get("inserted", 0),
        skipped=result.get("skipped", 0),
    )


class EulogyBatchRequest(BaseModel):
    """Optional override of the quarter and window.

    Default (none): run for the previous quarter ending at the start of the
    current one. Backfill: POST {"quarter": "2026-Q1",
    "period_start": "2026-01-01T00:00:00Z",
    "period_end": "2026-04-01T00:00:00Z"} to rerun a specific window.
    """

    quarter: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None


class EulogyBatchResponse(BaseModel):
    quarter: str
    period_start: datetime
    period_end: datetime
    eligible_users: int
    inserted: int
    skipped: int


@router.post(
    "/eulogy",
    response_model=EulogyBatchResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def eulogy(req: EulogyBatchRequest) -> EulogyBatchResponse:
    if req.quarter is None and req.period_start is None and req.period_end is None:
        result = await run_previous_quarter()
        quarter, start, end = previous_quarter_window(datetime.now(UTC))
    else:
        if not (req.quarter and req.period_start and req.period_end):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "quarter + period_start + period_end must be supplied together",
            )
        quarter, start, end = req.quarter, req.period_start, req.period_end
        result = await run_quarter(
            quarter=quarter, period_start=start, period_end=end
        )

    return EulogyBatchResponse(
        quarter=quarter,
        period_start=start,
        period_end=end,
        eligible_users=result.get("eligible_users", 0),
        inserted=result.get("inserted", 0),
        skipped=result.get("skipped", 0),
    )
