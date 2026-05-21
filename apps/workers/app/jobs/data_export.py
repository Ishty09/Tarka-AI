"""GDPR data-export job entry point (CLAUDE.md §27 step 57).

Wraps services.data_export.run_pending_batch so the cron route + any
manual admin trigger share the same defaults.
"""

from __future__ import annotations

from app.services.data_export import run_pending_batch

DEFAULT_BATCH_LIMIT = 10


async def run_now(*, limit: int = DEFAULT_BATCH_LIMIT) -> dict[str, int]:
    """One cron tick. Returns {processed, failed}."""

    return await run_pending_batch(limit=limit)
