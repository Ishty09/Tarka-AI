"""Couple-issue stale nudges.

Once an issue has been left in 'discussed' or 'agreed' for >
STALE_THRESHOLD_DAYS without being touched, send a push + email to
BOTH partners. Tracked via couple_issues.last_nudged_at so the same
stale window doesn't fire twice. When partners touch the issue
(bumping last_discussed_at) and let it go stale again, the cron
picks it up for a fresh nudge.

CLAUDE.md §1.11 — idempotency: we record per-user keys in
idempotency_keys via the push/email services. Within this service,
the last_nudged_at >= last_discussed_at check is the primary guard.

Out of scope: AI-assisted re-framing of the theme, escalation tiers
(could land later — gentle/pointed/brutal mirroring the Drill
Sergeant pattern).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.config import get_settings
from app.services._db_typing import row_or_none
from app.services._db_typing import rows as _rows
from app.services.email import send_email
from app.services.push import deliver_to_user
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


STALE_THRESHOLD_DAYS = 14


@dataclass(slots=True)
class IssueNudgeResult:
    eligible: int
    notified: int
    skipped: int


async def _resolve_email(supabase: Any, user_id: str) -> str | None:
    try:
        res = await supabase.auth.admin.get_user_by_id(user_id)
    except Exception as err:  # pragma: no cover - non-fatal
        log.info("issue_nudges.email_lookup_failed", user_id=user_id, error=str(err))
        return None
    user_obj = getattr(res, "user", None) or getattr(res, "data", None)
    email_val = getattr(user_obj, "email", None) if user_obj else None
    return email_val if isinstance(email_val, str) and email_val else None


async def run_nudges() -> IssueNudgeResult:
    """Scan active couple_issues for stale entries; notify + stamp."""

    supabase = await get_supabase()
    now = datetime.now(UTC)
    cutoff = (now - timedelta(days=STALE_THRESHOLD_DAYS)).isoformat()
    cutoff_iso = now.isoformat()

    # Issues stale AND not nudged for this stale window.
    # The "not nudged this window" predicate is:
    #   last_nudged_at IS NULL  OR  last_nudged_at < last_discussed_at
    # Supabase-py doesn't express the second branch easily, so we fetch
    # everything past the cutoff and filter in-process — at our volume
    # that's fine.
    resp = await (
        supabase.table("couple_issues")
        .select(
            "id, couple_link_id, theme, status, last_discussed_at, last_nudged_at"
        )
        .in_("status", ["discussed", "agreed"])
        .is_("resolved_at", None)
        .lt("last_discussed_at", cutoff)
        .execute()
    )
    candidates: list[dict[str, Any]] = list(_rows(resp))

    eligible = 0
    notified = 0
    skipped = 0
    app_url = str(get_settings().app_url).rstrip("/")

    for issue in candidates:
        last_discussed = issue.get("last_discussed_at")
        last_nudged = issue.get("last_nudged_at")
        if (
            last_nudged is not None
            and last_discussed is not None
            and last_nudged >= last_discussed
        ):
            # Already nudged for the current stale window — wait until
            # partners touch the issue before pinging again.
            skipped += 1
            continue
        eligible += 1

        link = row_or_none(
            await (
                supabase.table("couple_links")
                .select("user_a, user_b, status")
                .eq("id", issue["couple_link_id"])
                .single()
                .execute()
            )
        )
        if link is None or link.get("status") != "active":
            skipped += 1
            continue

        days_stale = _days_between(last_discussed, now)
        issues_url = f"{app_url}/couples/{issue['couple_link_id']}/issues"

        any_delivered = False
        for user_id in (link.get("user_a"), link.get("user_b")):
            if not user_id:
                continue
            try:
                results = await deliver_to_user(
                    user_id=user_id,
                    template="couples_issue_stale",
                    variables={
                        "theme": issue["theme"],
                        "days_stale": days_stale,
                    },
                    deep_link=issues_url,
                    idempotency_key=f"push:couples_issue_stale:{issue['id']}:{user_id}",
                    supabase=supabase,
                )
                if any(r.status in ("sent", "dry_run") for r in results):
                    any_delivered = True
            except Exception as err:  # pragma: no cover - non-fatal
                log.warning(
                    "issue_nudges.push_failed",
                    issue_id=issue["id"],
                    user_id=user_id,
                    error=str(err),
                )

            email_addr = await _resolve_email(supabase, user_id)
            if not email_addr:
                continue
            try:
                await send_email(
                    template="couples_issue_stale",
                    to_email=email_addr,
                    variables={
                        "theme": issue["theme"],
                        "days_stale": days_stale,
                        "issues_url": issues_url,
                    },
                    user_id=user_id,
                    idempotency_key=f"email:couples_issue_stale:{issue['id']}:{user_id}",
                    supabase=supabase,
                )
                any_delivered = True
            except Exception as err:  # pragma: no cover - non-fatal
                log.warning(
                    "issue_nudges.email_failed",
                    issue_id=issue["id"],
                    user_id=user_id,
                    error=str(err),
                )

        if any_delivered:
            notified += 1
            await (
                supabase.table("couple_issues")
                .update({"last_nudged_at": cutoff_iso})
                .eq("id", issue["id"])
                .execute()
            )
        else:
            # No active subscriptions on either side — don't burn the
            # nudge window; next run will re-evaluate.
            skipped += 1

    return IssueNudgeResult(eligible=eligible, notified=notified, skipped=skipped)


def _days_between(start_iso: str | None, now: datetime) -> int:
    if not start_iso:
        return STALE_THRESHOLD_DAYS
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    except ValueError:
        return STALE_THRESHOLD_DAYS
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    delta = now - start
    return max(0, int(delta.total_seconds() // 86_400))
