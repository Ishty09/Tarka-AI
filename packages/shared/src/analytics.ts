// Umami analytics event registry (CLAUDE.md §20, §27 step 61).
//
// Every event name shipped to Umami flows through this tuple so the TS
// caller side and the Python caller side stay aligned (the Python helper
// imports a copy of the same list — see apps/workers/app/services/analytics.py).
//
// Per §20 the event payload always carries: user_id (hashed), tier,
// locale, timestamp, plus per-event properties. The helpers in
// apps/web/lib/analytics and apps/workers/app/services/analytics merge
// the context block automatically.

export const ANALYTICS_EVENTS = [
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
] as const;

export type AnalyticsEvent = (typeof ANALYTICS_EVENTS)[number];
