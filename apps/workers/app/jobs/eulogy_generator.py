"""Quarterly Eulogy Test entry point (CLAUDE.md §27 step 20, §9.4.3).

Fires on the first day of each new quarter. The eulogy is for the quarter
that just ended — `previous_quarter_window(now)` gives us the slug, start,
and end. Callers can also pass an explicit quarter via the cron route for
manual backfill.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.eulogy import previous_quarter_window, run_quarter


async def run_previous_quarter() -> dict[str, int]:
    quarter, start, end = previous_quarter_window(datetime.now(UTC))
    return await run_quarter(quarter=quarter, period_start=start, period_end=end)
