"""Per-event notification preferences (§12.2).

Mirrors the categories declared in
`packages/shared/src/constants.ts`. profiles.notification_preferences
is shaped as { channel: { category: bool } }; a missing key means
allowed, explicit `false` mutes that channel+category pair. Global
profile.notification_push / notification_email remain the master
override.

Template → category maps for both channels live here so push.py and
email.py share the same source of truth. Some email templates are
ESSENTIAL (account, billing, security, safety) and bypass user prefs
entirely — represented as `None` category.

Keep NOTIFICATION_CATEGORIES in sync with the TS list (tests assert).
"""

from __future__ import annotations

from typing import Any, Literal

NotificationCategory = Literal[
    "daily_roast",
    "contradiction",
    "couples",
    "wagers",
    "mirror_eulogy",
    "streaks",
]


NOTIFICATION_CATEGORIES: tuple[NotificationCategory, ...] = (
    "daily_roast",
    "contradiction",
    "couples",
    "wagers",
    "mirror_eulogy",
    "streaks",
)


# Push templates. Every push template MUST appear here — the
# locale-completeness test in test_push uses PUSH_TEMPLATES; this map
# uses the same keys.
PUSH_TEMPLATE_CATEGORY: dict[str, NotificationCategory] = {
    "daily_roast": "daily_roast",
    "contradiction": "contradiction",
    "couples_invite": "couples",
    "couples_dispute_created": "couples",
    "couples_dispute_perspective_added": "couples",
    "couples_dispute_arbitrated": "couples",
    "couples_report_ready": "couples",
    "couples_prep_ready": "couples",
    "couples_issue_stale": "couples",
    "wager_checkin": "wagers",
    "wager_failed": "wagers",
    "mirror_ready": "mirror_eulogy",
    "eulogy_ready": "mirror_eulogy",
    "streak_punish": "streaks",
}


# Email templates. `None` = ESSENTIAL (account / billing / security /
# safety / required transactional). These always send regardless of
# user prefs; legally required (CAN-SPAM / GDPR carve-out) and
# operationally critical.
EMAIL_TEMPLATE_CATEGORY: dict[str, NotificationCategory | None] = {
    # Essential — never suppressed.
    "welcome": None,
    "magic_link": None,
    "subscription_confirmed": None,
    "subscription_canceled": None,
    "payment_failed": None,
    "data_export_ready": None,
    "account_deletion_grace_started": None,
    "emergency_contact_notification": None,
    "moderation_rejection": None,
    "beta_invite": None,
    # Engagement — gated by user prefs.
    "wager_won": "wagers",
    "wager_lost": "wagers",
    "couples_invite": "couples",
    "couples_dispute_created": "couples",
    "couples_dispute_perspective_added": "couples",
    "couples_dispute_arbitrated": "couples",
    "couples_report_ready": "couples",
    "couples_prep_ready": "couples",
    "couples_issue_stale": "couples",
    "mirror_report_ready": "mirror_eulogy",
    "eulogy_ready": "mirror_eulogy",
}


def prefs_allow(
    prefs: dict[str, Any] | None,
    *,
    channel: Literal["push", "email"],
    category: NotificationCategory,
) -> bool:
    """True unless prefs explicitly disable this (channel, category)."""

    if not prefs or not isinstance(prefs, dict):
        return True
    channel_prefs = prefs.get(channel)
    if not isinstance(channel_prefs, dict):
        return True
    val = channel_prefs.get(category)
    return val is not False


__all__ = [
    "EMAIL_TEMPLATE_CATEGORY",
    "NOTIFICATION_CATEGORIES",
    "NotificationCategory",
    "PUSH_TEMPLATE_CATEGORY",
    "prefs_allow",
]
