"""Daily Roast cron entry point (CLAUDE.md §27 step 29, §9.2.1).

Wakes up every 15 minutes. The actual scan + generation lives in
services/daily_roast.run_window.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.daily_roast import DEFAULT_WINDOW_MINUTES, run_window


async def run_now(*, window_minutes: int = DEFAULT_WINDOW_MINUTES) -> dict[str, int]:
    return await run_window(now_utc=datetime.now(UTC), window_minutes=window_minutes)
