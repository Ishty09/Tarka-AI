"""Safety incident persistence + crisis escalation (§6.6, §14, §11).

When chat receives an unsafe verdict, we write a safety_incidents row
so admins can review (§6.6 schema) AND, for crisis verdicts
specifically, escalate to the user's emergency contact when a
second crisis lands within 24 hours — the promise we made the user
at onboarding step 8.

Best-effort throughout: a failed insert or email never blocks the
refusal stream the chat route is about to return. The user message
is already persisted with the verdict stamped on it; safety_incidents
is the audit + escalation layer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

import structlog
from supabase import AsyncClient

from app.services._db_typing import row_or_none, rows as _rows
from app.services.email import send_email

log = structlog.get_logger(__name__)


IncidentCategory = Literal[
    "crisis",
    "abuse",
    "minor_self_sexualization",
    "jailbreak",
    "spam",
    "harassment",
]


# §13 spec: notify the emergency contact when the user expresses "clear
# crisis signals more than once in a 24-hour window." That's a 2nd crisis
# within 24h triggering the email.
CRISIS_WINDOW = timedelta(hours=24)
CRISIS_THRESHOLD = 2


async def record_incident(
    supabase: AsyncClient,
    *,
    user_id: str,
    conversation_id: str | None,
    message_id: int | None,
    category: IncidentCategory,
    verdict_reason: str,
    action_taken: str = "turn_refused",
) -> None:
    """Insert a safety_incidents row and — for crisis category only —
    check the 24h count and fire emergency_contact_notification when
    the threshold is met.
    """

    try:
        await (
            supabase.table("safety_incidents")
            .insert(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "category": category,
                    "verdict": verdict_reason,
                    "action_taken": action_taken,
                }
            )
            .execute()
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "safety_incidents.insert_failed",
            user_id=user_id,
            category=category,
            error=str(err),
        )
        return

    if category != "crisis":
        return

    # Count crisis incidents for this user within the trailing 24h
    # window. The fresh insert is included, so the threshold of 2 means
    # "this one plus at least one prior crisis in the last day."
    since = (datetime.now(UTC) - CRISIS_WINDOW).isoformat()
    try:
        res = (
            await supabase.table("safety_incidents")
            .select("id, created_at")
            .eq("user_id", user_id)
            .eq("category", "crisis")
            .gte("created_at", since)
            .limit(CRISIS_THRESHOLD + 5)
            .execute()
        )
        recent = list(_rows(res.data))
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "safety_incidents.count_failed", user_id=user_id, error=str(err)
        )
        return

    if len(recent) < CRISIS_THRESHOLD:
        return

    await _notify_emergency_contact(supabase, user_id=user_id)


async def _notify_emergency_contact(
    supabase: AsyncClient, *, user_id: str
) -> None:
    """Email the user's stated emergency contact. Skips cleanly when no
    contact is listed (free-tier or user opted out at onboarding).

    Idempotent per (user_id, UTC-date): once per user per day so a
    user in sustained crisis through several turns doesn't blast their
    contact every refusal — one notification is enough; the contact's
    job from there is the human follow-up.
    """

    profile_res = (
        await supabase.table("profiles")
        .select(
            "display_name, username, emergency_contact_name, "
            "emergency_contact_email"
        )
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    profile = row_or_none(profile_res.data) if profile_res is not None else None
    if profile is None:
        return

    contact_email = profile.get("emergency_contact_email")
    if not isinstance(contact_email, str) or not contact_email:
        # User didn't list anyone. Hotlines still surface inline in
        # the refusal stream — that's a separate, always-on safety
        # mechanism (crisis_hotlines table).
        log.info(
            "safety_incidents.no_emergency_contact",
            user_id=user_id,
        )
        return

    user_display = (
        profile.get("display_name")
        or profile.get("username")
        or "A Quarrel user"
    )
    today_utc = datetime.now(UTC).date().isoformat()

    try:
        await send_email(
            template="emergency_contact_notification",
            to_email=contact_email,
            variables={"user_display_name": user_display},
            user_id=user_id,
            idempotency_key=(
                f"email:emergency_contact_notification:{user_id}:{today_utc}"
            ),
            supabase=supabase,
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "safety_incidents.emergency_email_failed",
            user_id=user_id,
            error=str(err),
        )
