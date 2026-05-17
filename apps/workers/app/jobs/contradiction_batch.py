"""Nightly contradiction batch entry point (CLAUDE.md §9.4.1, §27 step 16).

The actual work lives in services/contradictions.run_batch — this module
exists so the routes/cron.py handler and any future scheduler (Trigger.dev,
pg_cron, manual admin trigger) share the same lookback semantics.

§7.2 says contradiction detection runs on quarrel-argue via OpenAI Batch
API. We're using real-time chat completions for MVP — the Batch API
integration is a follow-up optimisation that flips one model call site
without changing the surrounding flow.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.contradictions import run_batch


# Default lookback. The job is nominally nightly; a 25-hour window
# tolerates a missed run without dropping facts.
DEFAULT_LOOKBACK = timedelta(hours=25)


async def run_nightly(*, lookback: timedelta = DEFAULT_LOOKBACK) -> dict[str, int]:
    """One-shot nightly invocation. Returns counts for telemetry."""

    since = datetime.now(UTC) - lookback
    return await run_batch(since=since)
