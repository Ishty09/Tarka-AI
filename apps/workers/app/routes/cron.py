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
from app.jobs.daily_roast import run_now as run_daily_roast_now
from app.jobs.data_export import DEFAULT_BATCH_LIMIT
from app.jobs.data_export import run_now as run_data_export_now
from app.jobs.drill_sergeant_job import run_now as run_drill_sergeant_now
from app.jobs.eulogy_generator import run_previous_quarter
from app.jobs.mirror_mode_generator import WINDOW_DAYS, run_weekly_window
from app.jobs.wager_evaluator import run_today as run_wager_eval_today
from app.services.contradictions import run_batch
from app.services.daily_roast import DEFAULT_WINDOW_MINUTES
from app.services.daily_roast import run_window as run_daily_roast_window
from app.services.drill_sergeant import run_today as run_drill_sergeant_today
from app.services.eulogy import previous_quarter_window, run_quarter
from app.services.mirror import run_weekly as run_mirror_window
from app.services.wager_evaluator import run_due_evaluations

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


class DailyRoastRequest(BaseModel):
    """Optional override of the window length in minutes.

    Default (none): use DEFAULT_WINDOW_MINUTES (15). Backfill / re-fire:
    POST {"window_minutes": 60} expands the scan window for that run.
    """

    window_minutes: int | None = None
    now_utc: datetime | None = None


class DailyRoastResponse(BaseModel):
    now: datetime
    window_minutes: int
    eligible: int
    delivered: int
    skipped: int


@router.post(
    "/daily-roast",
    response_model=DailyRoastResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def daily_roast(req: DailyRoastRequest) -> DailyRoastResponse:
    minutes = req.window_minutes or DEFAULT_WINDOW_MINUTES
    if req.now_utc is None and req.window_minutes is None:
        result = await run_daily_roast_now()
        now = datetime.now(UTC)
    else:
        now = req.now_utc or datetime.now(UTC)
        result = await run_daily_roast_window(now_utc=now, window_minutes=minutes)

    return DailyRoastResponse(
        now=now,
        window_minutes=minutes,
        eligible=result.get("eligible", 0),
        delivered=result.get("delivered", 0),
        skipped=result.get("skipped", 0),
    )


class WagerEvalRequest(BaseModel):
    """Optional override of the cutoff date for backfill.

    Default (none): evaluate every active wager whose end_at <= today.
    Backfill: POST {"cutoff_date": "2026-05-01"} to evaluate wagers as
    if today were that date (re-runs are idempotent because the persist
    guard requires status='active').
    """

    cutoff_date: str | None = None


class WagerEvalResponse(BaseModel):
    cutoff: str
    candidates: int
    succeeded: int
    failed: int
    skipped: int


@router.post(
    "/wager-evaluator",
    response_model=WagerEvalResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def wager_evaluator(req: WagerEvalRequest) -> WagerEvalResponse:
    from datetime import date as _date

    if req.cutoff_date is None:
        result = await run_wager_eval_today()
        cutoff_iso = datetime.now(UTC).date().isoformat()
    else:
        try:
            cutoff = _date.fromisoformat(req.cutoff_date)
        except ValueError as err:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "invalid_cutoff_date"
            ) from err
        result = await run_due_evaluations(cutoff_date=cutoff)
        cutoff_iso = cutoff.isoformat()

    return WagerEvalResponse(
        cutoff=cutoff_iso,
        candidates=result.get("candidates", 0),
        succeeded=result.get("succeeded", 0),
        failed=result.get("failed", 0),
        skipped=result.get("skipped", 0),
    )


class DrillSergeantRequest(BaseModel):
    """Optional override of `today` for backfill or test fires."""

    today: str | None = None


class DrillSergeantResponse(BaseModel):
    today: str
    candidates: int
    delivered: int
    skipped: int


@router.post(
    "/drill-sergeant",
    response_model=DrillSergeantResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def drill_sergeant(req: DrillSergeantRequest) -> DrillSergeantResponse:
    from datetime import date as _date

    if req.today is None:
        result = await run_drill_sergeant_now()
        today_iso = datetime.now(UTC).date().isoformat()
    else:
        try:
            today_d = _date.fromisoformat(req.today)
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_today") from err
        result = await run_drill_sergeant_today(today=today_d)
        today_iso = today_d.isoformat()

    return DrillSergeantResponse(
        today=today_iso,
        candidates=result.get("candidates", 0),
        delivered=result.get("delivered", 0),
        skipped=result.get("skipped", 0),
    )


class DataExportRequest(BaseModel):
    """Optional override of the per-tick batch size.

    Default (none): DEFAULT_BATCH_LIMIT pending requests per call. A
    scheduler firing every minute will drain the queue at limit/min.
    """

    limit: int | None = None


class DataExportResponse(BaseModel):
    limit: int
    processed: int
    failed: int


@router.post(
    "/data-export",
    response_model=DataExportResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def data_export(req: DataExportRequest) -> DataExportResponse:
    limit = req.limit if req.limit and req.limit > 0 else DEFAULT_BATCH_LIMIT
    if req.limit is None:
        result = await run_data_export_now()
    else:
        result = await run_data_export_now(limit=limit)
    return DataExportResponse(
        limit=limit,
        processed=result.get("processed", 0),
        failed=result.get("failed", 0),
    )
