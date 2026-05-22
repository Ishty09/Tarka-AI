"""Server-side Umami event helper (CLAUDE.md §20, §27 step 61).

POSTs to the Umami /api/send collect endpoint. Mirrors apps/web/lib/
analytics/server.ts so events fired from worker jobs look the same as
events from the web app.

Failure mode: any error is swallowed and logged — analytics must never
break the underlying business flow.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

import httpx
import structlog

from app.config import get_settings

log = structlog.get_logger(__name__)


# Mirror of packages/shared/src/analytics.ts. Keep in lockstep.
ANALYTICS_EVENTS: tuple[str, ...] = (
    "signup_started",
    "signup_completed",
    "onboarding_completed",
    "chat_message_sent",
    "chat_message_received",
    "persona_installed",
    "persona_created",
    "persona_published",
    "couple_link_created",
    "couple_link_accepted",
    "couple_cross_fact_enabled",
    "group_room_created",
    "group_room_joined",
    "wager_created",
    "wager_payment_confirmed",
    "wager_checkin",
    "wager_succeeded",
    "wager_failed",
    "roast_feed_post_created",
    "roast_feed_post_upvoted",
    "contradiction_surfaced",
    "contradiction_dismissed",
    "mirror_report_viewed",
    "eulogy_viewed",
    "decision_killer_used",
    "cope_detector_used",
    "council_run",
    "steelman_used",
    "breakup_analyzer_used",
    "negotiation_sparring_started",
    "drill_sergeant_streak_started",
    "upgrade_clicked",
    "upgrade_completed",
    "downgrade_clicked",
    "downgrade_completed",
    "data_export_requested",
    "account_deletion_requested",
    "crisis_resource_shown",
    "emergency_contact_notified",
    "quota_429",
    "fallback_used",
)


Tier = Literal["free", "pro", "max"]


def hash_user_id(user_id: str | None) -> str | None:
    """Hash uuid → 16-char hex prefix; matches apps/web hashUserId."""

    if not user_id:
        return None
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]


def _collect_endpoint() -> str | None:
    settings = get_settings()
    script_url = settings.umami_script_url
    if not script_url:
        return None
    if script_url.endswith("/script.js"):
        return script_url[: -len("/script.js")] + "/api/send"
    return script_url.rstrip("/") + "/api/send"


def _hostname() -> str | None:
    settings = get_settings()
    if not settings.app_url:
        return None
    return settings.app_url.host


async def track_server(
    event: str,
    *,
    user_id: str | None = None,
    tier: Tier | None = None,
    locale: str | None = None,
    data: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Fire-and-forget. Never raises into business logic."""

    if event not in ANALYTICS_EVENTS:
        log.warning("analytics.unknown_event", event=event)
        return

    settings = get_settings()
    if not settings.umami_website_id:
        return
    endpoint = _collect_endpoint()
    if endpoint is None:
        return

    payload_data: dict[str, Any] = dict(data or {})
    if user_id:
        payload_data["user_id"] = hash_user_id(user_id)
    if tier:
        payload_data["tier"] = tier
    if locale:
        payload_data["locale"] = locale

    body = {
        "type": "event",
        "payload": {
            "website": settings.umami_website_id,
            "name": event,
            "data": payload_data,
            "hostname": _hostname(),
            "language": locale,
            "url": payload_data.get("url", "/"),
        },
    }

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=5.0)
    try:
        await http.post(
            endpoint,
            headers={
                "content-type": "application/json",
                "user-agent": "Quarrel/1.0 (+workers)",
            },
            json=body,
        )
    except Exception as err:
        log.warning("analytics.send_failed", event=event, error=str(err))
    finally:
        if own_client:
            await http.aclose()
