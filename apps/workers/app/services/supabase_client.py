"""Async Supabase client (service-role) singleton.

Workers use the service-role key because most paths run server-to-server
without an authenticated user JWT — e.g. cron jobs, batch contradiction
detection, webhook handlers (§3, §22). For chat traffic that DOES carry a
user identity (forwarded from apps/web), we still write with service-role
but verify the user owns the row in code before writing — RLS is duplicated
in the application layer to keep service-role from becoming a back door.

CLAUDE.md §1.3: service-role key NEVER lives in apps/web. This is the only
process that ever reads it.
"""

from __future__ import annotations

from supabase import AsyncClient, acreate_client

from app.config import get_settings

_singleton: AsyncClient | None = None


async def get_supabase() -> AsyncClient:
    """Lazy singleton — created on first use."""

    global _singleton
    if _singleton is None:
        settings = get_settings()
        _singleton = await acreate_client(
            str(settings.supabase_url),
            settings.supabase_service_role_key,
        )
    return _singleton


def set_supabase(client: AsyncClient | None) -> None:
    """Test hook: substitute or clear the cached client."""

    global _singleton
    _singleton = client
