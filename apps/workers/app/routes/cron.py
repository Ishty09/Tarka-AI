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
from app.jobs.account_deletion import run_now as run_account_deletion_now
from app.jobs.beta_invites import (
    DEFAULT_BATCH_LIMIT as DEFAULT_BETA_INVITE_LIMIT,
)
from app.jobs.beta_invites import run_now as run_beta_invites_now
from app.jobs.contradiction_batch import DEFAULT_LOOKBACK, run_nightly
from app.jobs.daily_roast import run_now as run_daily_roast_now
from app.jobs.data_export import DEFAULT_BATCH_LIMIT
from app.jobs.data_export import run_now as run_data_export_now
from app.jobs.drill_sergeant_job import run_now as run_drill_sergeant_now
from app.jobs.eulogy_generator import run_previous_quarter
from app.jobs.mirror_mode_generator import WINDOW_DAYS, run_weekly_window
from app.jobs.wager_evaluator import run_today as run_wager_eval_today
from app.services.contradictions import run_batch
from app.services.couples_report import run_weekly as run_couples_report_weekly
from app.services.daily_roast import DEFAULT_WINDOW_MINUTES
from app.services.issue_nudges import run_nudges as run_issue_nudges
from app.services.daily_roast import run_window as run_daily_roast_window
from app.services.drill_sergeant import run_today as run_drill_sergeant_today
from app.services.eulogy import previous_quarter_window, run_quarter
from app.services.mirror import run_weekly as run_mirror_window
from app.services.wager_checkin_nudges import run_nudges as run_wager_checkin_nudges
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


class AccountDeletionResponse(BaseModel):
    notified: int
    notify_failed: int
    candidates: int
    deleted: int
    delete_failed: int


@router.post(
    "/account-deletion",
    response_model=AccountDeletionResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def account_deletion() -> AccountDeletionResponse:
    result = await run_account_deletion_now()
    return AccountDeletionResponse(
        notified=result.get("notified", 0),
        notify_failed=result.get("notify_failed", 0),
        candidates=result.get("candidates", 0),
        deleted=result.get("deleted", 0),
        delete_failed=result.get("delete_failed", 0),
    )


class BetaInvitesRequest(BaseModel):
    """Optional override of the per-tick send budget.

    Default (none): DEFAULT_BETA_INVITE_LIMIT. Used to drain the
    `beta_invites` queue Supabase admin links are rate-limited, so the
    job processes invites sequentially within each tick.
    """

    limit: int | None = None


class BetaInvitesResponse(BaseModel):
    limit: int
    queued: int
    sent: int
    failed: int


@router.post(
    "/beta-invites",
    response_model=BetaInvitesResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def beta_invites(req: BetaInvitesRequest) -> BetaInvitesResponse:
    limit = req.limit if req.limit and req.limit > 0 else DEFAULT_BETA_INVITE_LIMIT
    if req.limit is None:
        result = await run_beta_invites_now()
    else:
        result = await run_beta_invites_now(limit=limit)
    return BetaInvitesResponse(
        limit=limit,
        queued=result.get("queued", 0),
        sent=result.get("sent", 0),
        failed=result.get("failed", 0),
    )


# ----- Couples weekly report (§9.3.x Week 3) ---------------------------------


class CouplesReportResponse(BaseModel):
    period_start: str
    period_end: str
    eligible_couples: int
    inserted: int
    skipped: int


@router.post(
    "/couples-report",
    response_model=CouplesReportResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def couples_report() -> CouplesReportResponse:
    """Generate weekly couples reports for the trailing 7 days.

    Idempotent per (couple_link_id, period_start). Safe to retry — already-
    generated couples skip. Couples with no activity also skip.
    """

    result = await run_couples_report_weekly()
    return CouplesReportResponse(
        period_start=result.period_start.isoformat(),
        period_end=result.period_end.isoformat(),
        eligible_couples=result.eligible,
        inserted=result.inserted,
        skipped=result.skipped,
    )


# ----- Couples open-issues stale nudge (§9.3.x Week 4 follow-up) -----------


class IssueNudgeResponse(BaseModel):
    eligible_issues: int
    notified: int
    skipped: int


@router.post(
    "/couple-issue-nudges",
    response_model=IssueNudgeResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def couple_issue_nudges() -> IssueNudgeResponse:
    """Nudge both partners on couple_issues stale for >14 days.

    Idempotent at the issue level via last_nudged_at — once nudged for
    a stale window, the issue won't fire again unless partners touch
    it (bumping last_discussed_at) and let it go stale again.
    """

    result = await run_issue_nudges()
    return IssueNudgeResponse(
        eligible_issues=result.eligible,
        notified=result.notified,
        skipped=result.skipped,
    )


# ----- Wager daily check-in nudges (§9.5.5, §13 push.wager_checkin) --------


class WagerCheckinNudgeResponse(BaseModel):
    eligible_wagers: int
    sent: int
    skipped: int


@router.post(
    "/wager-checkin-nudges",
    response_model=WagerCheckinNudgeResponse,
    dependencies=[Depends(_verify_cron_secret)],
)
async def wager_checkin_nudges() -> WagerCheckinNudgeResponse:
    """Daily push to users with active wagers who haven't checked in yet.

    One push per active wager (each has its own goal + stake). Skips
    wagers that already have a wager_checkins row for today, regardless
    of status. Idempotent at (wager_id, today) so cron retries on the
    same day don't double-fire.
    """

    result = await run_wager_checkin_nudges()
    return WagerCheckinNudgeResponse(
        eligible_wagers=result.eligible,
        sent=result.sent,
        skipped=result.skipped,
    )
