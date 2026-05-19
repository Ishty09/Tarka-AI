"""Drill Sergeant cron entry point (CLAUDE.md §27 step 41, §9.5.4)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.drill_sergeant import run_today


async def run_now() -> dict[str, int]:
    return await run_today(today=datetime.now(UTC).date())
