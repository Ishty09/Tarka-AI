"""Wager evaluator cron entry point (CLAUDE.md §27 step 40, §9.5.5).

Fires daily. Picks up every active wager whose end_at has passed and
runs the §9.5.5 evaluation pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.wager_evaluator import run_due_evaluations


async def run_today() -> dict[str, int]:
    return await run_due_evaluations(cutoff_date=datetime.now(UTC).date())
