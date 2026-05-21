"""Account-deletion sweeper job entry point (CLAUDE.md §27 step 58).

Wraps services.account_deletion.run_once with the cron-route defaults.
A scheduler firing this every 15 minutes drains the notification phase
roughly in real time and runs the hard-delete sweep on the same cadence
without straining auth admin.
"""

from __future__ import annotations

from app.services.account_deletion import run_once

DEFAULT_NOTIFY_LIMIT = 100
DEFAULT_DELETE_LIMIT = 50


async def run_now() -> dict[str, int]:
    return await run_once(
        notify_limit=DEFAULT_NOTIFY_LIMIT,
        delete_limit=DEFAULT_DELETE_LIMIT,
    )
