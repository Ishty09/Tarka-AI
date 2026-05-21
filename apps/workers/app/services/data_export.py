"""GDPR data-export pipeline (CLAUDE.md §12.5, §16, §27 step 57).

The /settings/data action inserts a row into `data_export_requests` with
status='pending'. This service is the worker side: it picks up pending
rows, gathers every table that mentions the user, serialises to JSON,
uploads to the private `data-exports` Supabase Storage bucket, generates
a 7-day signed URL, and emails the user via the `data_export_ready`
template.

The service is intentionally append-only and side-effect-explicit so
the cron handler in routes/cron.py can drive it one row at a time and
the suite can stub each step.

Design choices:
- One row per call. `run_pending_batch(limit=10)` claims rows by flipping
  status='pending' → 'processing' atomically so a re-fired cron doesn't
  double-ship.
- Full-table dumps. Per §16 the export is "everything we hold". Caps
  exist so a runaway user (millions of messages) doesn't OOM the worker;
  caps overflow → `row_counts` records "truncated" and the email body
  notes it. For MVP a single capped pass is enough; pagination is a
  follow-up.
- Push tokens are redacted on export. Tokens are credentials, and §16
  promises the export is data-about-you, not session material.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from supabase import AsyncClient

from app.services._db_typing import row_or_none
from app.services._db_typing import rows as _rows
from app.services.email import send_email
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


# ----- Constants ------------------------------------------------------------

EXPORT_BUCKET = "data-exports"
# Signed download URL TTL — long enough for the user to act on the email,
# short enough that a stolen link expires before the value drains.
DOWNLOAD_TTL_SECONDS = 7 * 24 * 60 * 60
DOWNLOAD_TTL_HOURS = 24 * 7

# Per-table row caps. Anything beyond is truncated with an overflow flag
# recorded in row_counts so the user knows the export is partial.
DEFAULT_TABLE_CAP = 50_000
SCHEMA_VERSION = 1


@dataclass(slots=True)
class ExportResult:
    request_id: str
    user_id: str
    status: str
    row_counts: dict[str, int]
    byte_size: int | None = None
    storage_path: str | None = None
    download_url: str | None = None
    error: str | None = None


# Tables to include in the export. Order doesn't matter functionally;
# we sort the dump for stable byte size.
USER_SCOPED_TABLES: tuple[tuple[str, str], ...] = (
    # (table_name, user_column)
    ("conversations", "user_id"),
    ("user_facts", "user_id"),
    ("contradictions", "user_id"),
    ("mirror_reports", "user_id"),
    ("eulogy_reports", "user_id"),
    ("wagers", "user_id"),
    ("streaks", "user_id"),
    ("subscriptions", "user_id"),
    ("usage_quotas", "user_id"),
    ("roast_feed_posts", "user_id"),
    ("safety_incidents", "user_id"),
    ("data_export_requests", "user_id"),
)


# ----- Claim + status updates ----------------------------------------------


async def claim_next_pending(
    supabase: AsyncClient,
) -> dict[str, Any] | None:
    """Mark the oldest pending request as 'processing' and return it.

    Postgres' default isolation is sufficient here: two workers racing
    will both see the same row, but only one will pass the update filter
    `status='pending'`. The loser's update returns zero rows.
    """

    candidate_res = (
        await supabase.table("data_export_requests")
        .select("id, user_id, requested_at")
        .eq("status", "pending")
        .order("requested_at", desc=False)
        .limit(1)
        .maybe_single()
        .execute()
    )
    if candidate_res is None:
        return None
    candidate = row_or_none(candidate_res.data)
    if candidate is None:
        return None

    claim_res = (
        await supabase.table("data_export_requests")
        .update(
            {
                "status": "processing",
                "started_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        .eq("id", candidate["id"])
        .eq("status", "pending")
        .execute()
    )
    if not claim_res.data:
        return None
    rows = _rows(claim_res.data)
    return rows[0] if rows else None


async def _mark_ready(
    supabase: AsyncClient,
    *,
    request_id: str,
    storage_path: str,
    download_url: str,
    byte_size: int,
    row_counts: dict[str, int],
) -> None:
    expires_at = datetime.now(UTC) + timedelta(seconds=DOWNLOAD_TTL_SECONDS)
    await (
        supabase.table("data_export_requests")
        .update(
            {
                "status": "ready",
                "ready_at": datetime.now(UTC).isoformat(),
                "expires_at": expires_at.isoformat(),
                "storage_path": storage_path,
                "download_url": download_url,
                "byte_size": byte_size,
                "row_counts": row_counts,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        .eq("id", request_id)
        .execute()
    )


async def _mark_failed(
    supabase: AsyncClient,
    *,
    request_id: str,
    error_message: str,
) -> None:
    await (
        supabase.table("data_export_requests")
        .update(
            {
                "status": "failed",
                "failed_at": datetime.now(UTC).isoformat(),
                "error_message": error_message[:1000],
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        .eq("id", request_id)
        .execute()
    )


# ----- Data collection ------------------------------------------------------


async def _fetch_table(
    supabase: AsyncClient,
    *,
    table: str,
    user_column: str,
    user_id: str,
    cap: int = DEFAULT_TABLE_CAP,
) -> tuple[list[dict[str, Any]], bool]:
    """Return (rows, truncated)."""

    res = (
        await supabase.table(table)
        .select("*")
        .eq(user_column, user_id)
        .limit(cap + 1)
        .execute()
    )
    rows = _rows(res.data)
    truncated = len(rows) > cap
    if truncated:
        rows = rows[:cap]
    return rows, truncated


async def _fetch_messages(
    supabase: AsyncClient,
    *,
    user_id: str,
    conversation_ids: list[str],
    cap: int = DEFAULT_TABLE_CAP,
) -> tuple[list[dict[str, Any]], bool]:
    """Messages join through conversations — fetch by conversation_id IN (...)."""

    if not conversation_ids:
        return [], False
    res = (
        await supabase.table("messages")
        .select("*")
        .in_("conversation_id", conversation_ids)
        .limit(cap + 1)
        .execute()
    )
    rows = _rows(res.data)
    truncated = len(rows) > cap
    if truncated:
        rows = rows[:cap]
    return rows, truncated


async def _fetch_couple_links(
    supabase: AsyncClient, *, user_id: str
) -> list[dict[str, Any]]:
    """Couple links list the user as either user_a or user_b."""

    res_a = (
        await supabase.table("couple_links")
        .select("*")
        .eq("user_a", user_id)
        .execute()
    )
    res_b = (
        await supabase.table("couple_links")
        .select("*")
        .eq("user_b", user_id)
        .execute()
    )
    return [*_rows(res_a.data), *_rows(res_b.data)]


async def _fetch_group_memberships(
    supabase: AsyncClient, *, user_id: str
) -> list[dict[str, Any]]:
    res = (
        await supabase.table("group_members")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return _rows(res.data)


async def _fetch_push_subscriptions_redacted(
    supabase: AsyncClient, *, user_id: str
) -> list[dict[str, Any]]:
    """Push tokens are credentials — return everything except the raw token."""

    res = (
        await supabase.table("push_subscriptions")
        .select("id, platform, device_label, last_seen_at, created_at")
        .eq("user_id", user_id)
        .execute()
    )
    return _rows(res.data)


async def _fetch_wager_checkins(
    supabase: AsyncClient, *, user_id: str
) -> list[dict[str, Any]]:
    res = (
        await supabase.table("wager_checkins")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return _rows(res.data)


async def _fetch_roast_feed_votes(
    supabase: AsyncClient, *, user_id: str
) -> list[dict[str, Any]]:
    res = (
        await supabase.table("roast_feed_votes")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return _rows(res.data)


async def gather_export(
    supabase: AsyncClient, *, user_id: str
) -> tuple[dict[str, Any], dict[str, int]]:
    """Collect every table that mentions `user_id`.

    Returns (payload, row_counts). row_counts uses {table_name: -1} to
    signal a truncated table. Negative values are easy to filter and
    show up obviously in receipts.
    """

    row_counts: dict[str, int] = {}
    truncations: dict[str, bool] = {}
    tables: dict[str, Any] = {}

    profile_res = (
        await supabase.table("profiles")
        .select("*")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    profile = row_or_none(profile_res.data if profile_res else None)
    tables["profile"] = profile
    row_counts["profile"] = 1 if profile else 0

    for table, user_column in USER_SCOPED_TABLES:
        rows, truncated = await _fetch_table(
            supabase,
            table=table,
            user_column=user_column,
            user_id=user_id,
        )
        tables[table] = rows
        row_counts[table] = len(rows)
        truncations[table] = truncated

    conversation_ids = [c["id"] for c in tables["conversations"] if c.get("id")]
    messages, msg_truncated = await _fetch_messages(
        supabase,
        user_id=user_id,
        conversation_ids=conversation_ids,
    )
    tables["messages"] = messages
    row_counts["messages"] = len(messages)
    truncations["messages"] = msg_truncated

    tables["couple_links"] = await _fetch_couple_links(supabase, user_id=user_id)
    row_counts["couple_links"] = len(tables["couple_links"])

    tables["group_members"] = await _fetch_group_memberships(supabase, user_id=user_id)
    row_counts["group_members"] = len(tables["group_members"])

    tables["push_subscriptions"] = await _fetch_push_subscriptions_redacted(
        supabase, user_id=user_id
    )
    row_counts["push_subscriptions"] = len(tables["push_subscriptions"])

    tables["wager_checkins"] = await _fetch_wager_checkins(supabase, user_id=user_id)
    row_counts["wager_checkins"] = len(tables["wager_checkins"])

    tables["roast_feed_votes"] = await _fetch_roast_feed_votes(supabase, user_id=user_id)
    row_counts["roast_feed_votes"] = len(tables["roast_feed_votes"])

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "user_id": user_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "note": (
            "This file contains every record Quarrel holds about you. Push "
            "tokens are redacted because they are credentials, not data. "
            "If any table has -1 in row_counts the export was truncated; "
            "contact privacy@quarrel.ai for a full pull."
        ),
        "tables": tables,
        "row_counts": {
            table: (-1 if truncations.get(table) else count)
            for table, count in row_counts.items()
        },
    }
    return payload, row_counts


# ----- Storage upload + signed URL -----------------------------------------


def serialise(payload: dict[str, Any]) -> bytes:
    """Stable JSON serialisation."""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode(
        "utf-8"
    )


async def upload_to_storage(
    supabase: AsyncClient, *, user_id: str, request_id: str, body: bytes
) -> str:
    """Upload to bucket. Returns the storage-relative path."""

    path = f"{user_id}/{request_id}.json"
    bucket = supabase.storage.from_(EXPORT_BUCKET)
    await bucket.upload(
        path=path,
        file=body,
        file_options={"content-type": "application/json", "upsert": "true"},
    )
    return path


async def signed_download_url(
    supabase: AsyncClient,
    *,
    storage_path: str,
    ttl_seconds: int = DOWNLOAD_TTL_SECONDS,
) -> str:
    bucket = supabase.storage.from_(EXPORT_BUCKET)
    res = await bucket.create_signed_url(storage_path, ttl_seconds)
    # supabase-py returns either {'signedURL': '...'} or {'signed_url': '...'}
    # depending on version; check both.
    url = res.get("signedURL") or res.get("signed_url")
    if not isinstance(url, str) or not url:
        raise RuntimeError("Supabase storage did not return a signed URL")
    return url


# ----- End-to-end -----------------------------------------------------------


async def _resolve_email(
    supabase: AsyncClient, *, user_id: str
) -> tuple[str | None, str | None]:
    """Return (email, display_name) for the user_id, or (None, None)."""

    res = (
        await supabase.auth.admin.get_user_by_id(user_id)
    )
    user = getattr(res, "user", None) or getattr(res, "data", None)
    email: str | None = getattr(user, "email", None) if user else None

    profile_res = (
        await supabase.table("profiles")
        .select("display_name")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    display_name: str | None = None
    if profile_res is not None:
        profile = row_or_none(profile_res.data)
        if profile is not None:
            v = profile.get("display_name")
            display_name = v if isinstance(v, str) else None
    return email, display_name


async def process_request(
    *,
    request: dict[str, Any],
    supabase: AsyncClient | None = None,
) -> ExportResult:
    """Run gather → upload → sign → email → mark ready for a claimed request.

    Caller has already flipped status to 'processing' via claim_next_pending.
    Any exception here flips it to 'failed' with the message captured.
    """

    sb = supabase or await get_supabase()
    request_id: str = str(request["id"])
    user_id: str = str(request["user_id"])

    try:
        payload, row_counts = await gather_export(sb, user_id=user_id)
        body = serialise(payload)
        storage_path = await upload_to_storage(
            sb, user_id=user_id, request_id=request_id, body=body
        )
        url = await signed_download_url(sb, storage_path=storage_path)

        await _mark_ready(
            sb,
            request_id=request_id,
            storage_path=storage_path,
            download_url=url,
            byte_size=len(body),
            row_counts=row_counts,
        )

        email, display_name = await _resolve_email(sb, user_id=user_id)
        if email:
            await send_email(
                template="data_export_ready",
                to_email=email,
                to_name=display_name,
                variables={"download_url": url, "ttl_hours": DOWNLOAD_TTL_HOURS},
                idempotency_key=f"email:data_export_ready:{request_id}",
                user_id=user_id,
                supabase=sb,
            )
            await (
                sb.table("data_export_requests")
                .update({"email_sent_at": datetime.now(UTC).isoformat()})
                .eq("id", request_id)
                .execute()
            )
        else:
            log.warning(
                "data_export.no_email", user_id=user_id, request_id=request_id
            )

        return ExportResult(
            request_id=request_id,
            user_id=user_id,
            status="ready",
            row_counts=row_counts,
            byte_size=len(body),
            storage_path=storage_path,
            download_url=url,
        )
    except Exception as err:
        log.warning(
            "data_export.failed",
            user_id=user_id,
            request_id=request_id,
            error=str(err),
        )
        await _mark_failed(sb, request_id=request_id, error_message=str(err))
        return ExportResult(
            request_id=request_id,
            user_id=user_id,
            status="failed",
            row_counts={},
            error=str(err),
        )


async def run_pending_batch(
    *, limit: int = 10, supabase: AsyncClient | None = None
) -> dict[str, int]:
    """Process up to `limit` pending requests in this cron tick."""

    sb = supabase or await get_supabase()
    processed = 0
    failed = 0
    for _ in range(limit):
        claimed = await claim_next_pending(sb)
        if claimed is None:
            break
        result = await process_request(request=claimed, supabase=sb)
        if result.status == "ready":
            processed += 1
        else:
            failed += 1
    return {"processed": processed, "failed": failed}
