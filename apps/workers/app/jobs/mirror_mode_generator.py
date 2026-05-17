"""Weekly Mirror Mode entry point (CLAUDE.md §27 step 19, §9.4.2).

The actual generation lives in services/mirror.run_weekly — this module
exists so cron + admin triggers + tests share the same lookback semantics.

§9.4.2 schedules "weekly cron Sunday 09:00 UTC per user timezone". The
per-timezone variant is a refinement we don't have infrastructure for yet
(no per-user cron); this job uses a single fixed window (the prior 7 days
ending at the moment of invocation) and the scheduler decides when to fire.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.mirror import run_weekly


WINDOW_DAYS = 7


async def run_weekly_window() -> dict[str, int]:
    """Generate reports for the trailing 7-day window."""

    end = datetime.now(UTC)
    start = end - timedelta(days=WINDOW_DAYS)
    return await run_weekly(period_start=start, period_end=end)
