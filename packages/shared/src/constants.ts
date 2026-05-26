// App-wide constants. Where a constant duplicates a CHECK constraint or a
// migration value, keep this file the SECONDARY source — schemas in
// supabase/migrations are authoritative; this exists for ergonomic enumeration
// in TS code (sidebars, dropdowns, route params, etc.).

export const APP_NAME = "Quarrel";
export const APP_CODENAME = "Tarka";
export const APP_TAGLINE = "The AI that won't let you lie to yourself.";

// ----- Tier + mode literals --------------------------------------------------

export const TIERS = ["free", "pro", "max"] as const;
export type Tier = (typeof TIERS)[number];

export const MODES = [
  "argue",
  "roast",
  "mediate",
  "council",
  "negotiate",
  "custom",
  "roast_my_x",
  "decision_killer",
  "cope_detector",
  "steelman",
  "future_self",
  "past_self",
  "drill_sergeant",
] as const;
export type Mode = (typeof MODES)[number];

// ----- Locales (§10 — 16 launch locales) ------------------------------------

export const LOCALES = [
  "en",
  "bn",
  "hi",
  "es",
  "pt",
  "it",
  "ru",
  "ar",
  "ko",
  "ja",
  "de",
  "fr",
  "zh",
  "id",
  "vi",
  "he",
] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

// ----- Council roster (§9.1.2) ----------------------------------------------

export const COUNCIL_ROSTER = [
  "the_stoic",
  "the_economist",
  "the_therapist",
  "the_skeptic",
  "the_insider",
] as const;
export type CouncilMember = (typeof COUNCIL_ROSTER)[number];

// ----- Roast My X programmatic-SEO targets (§9.2.2) -------------------------

export const ROAST_TARGETS = [
  "linkedin",
  "twitter",
  "resume",
  "github-pr",
  "dating-profile",
  "cover-letter",
  "code",
  "instagram",
  "portfolio",
  "startup-idea",
  "email-draft",
  "tweet",
  "business-name",
  "pitch-deck",
  "essay",
  "resignation-letter",
  "apology",
  "dating-bio",
  "linkedin-post",
  "wedding-speech",
] as const;
export type RoastTarget = (typeof ROAST_TARGETS)[number];

// ----- Drill Sergeant escalation (§9.5.4) -----------------------------------

export const DRILL_SERGEANT_ESCALATION = [
  { day_missed: 1, tone: "gentle" },
  { day_missed: 3, tone: "pointed" },
  { day_missed: 7, tone: "brutal" },
  { day_missed: 14, tone: "eulogy" },
] as const;

// ----- Tier limits (§8.1) ---------------------------------------------------
// Limits are read by apps/workers/services/quotas.py and surfaced in the UI.
// `null` = unlimited (Max tier "unlimited" cells).

type CouncilLimit = { period: "day" | "week"; limit: number };

interface TierLimit {
  messages_per_day: number;
  council_runs: CouncilLimit;
  /** Created + installed combined. */
  active_personas: number | null;
  couple_links_active: number;
  /** null = unlimited. Per-month cap on couples disputes the user can
   *  CREATE. Reading + adding perspective on partner-created disputes
   *  doesn't count against the creator's quota. */
  couple_disputes_per_month: number | null;
  /** null = unlimited. Per-month cap on private pre-conversation preps. */
  couple_preps_per_month: number | null;
  group_seats_per_room: number;
  wager_active_stakes: number;
  /** USD cents; 0 means wagers disabled at this tier. */
  wager_max_stake_cents: number;
  /** 0 means read-only feed at this tier. */
  roast_feed_posts_per_week: number;
  /** USD cents/month; 0 means marketplace earnings disabled. */
  persona_earnings_cap_cents_per_month: number;
  /** null = forever. */
  contradiction_wall_depth_days: number | null;
  context_window_tokens: number;
  /** Mirror Mode behaviour: read-only-past, weekly, weekly+on-demand. */
  mirror_mode: "read_past_only" | "weekly" | "weekly_and_on_demand";
  /** Eulogy Test cadence. null = disabled. */
  eulogy_cadence: "quarterly" | "quarterly_and_on_demand" | null;
  voice_minutes_per_month: number;
  /** null = unlimited. */
  drill_sergeant_scheduled: number | null;
}

export const TIER_LIMITS: Record<Tier, TierLimit> = {
  free: {
    messages_per_day: 15,
    council_runs: { period: "week", limit: 1 },
    active_personas: 2,
    // Couples is Quarrel's flagship — free users get 1 active link to
    // try, with tight per-month caps on the AI-expensive operations
    // (disputes + preps) so the upgrade lever stays strong.
    couple_links_active: 1,
    couple_disputes_per_month: 2,
    couple_preps_per_month: 1,
    group_seats_per_room: 0,
    wager_active_stakes: 0,
    wager_max_stake_cents: 0,
    roast_feed_posts_per_week: 0,
    persona_earnings_cap_cents_per_month: 0,
    contradiction_wall_depth_days: 30,
    context_window_tokens: 8_000,
    mirror_mode: "read_past_only",
    eulogy_cadence: null,
    voice_minutes_per_month: 2,
    drill_sergeant_scheduled: 1,
  },
  pro: {
    messages_per_day: 200,
    council_runs: { period: "day", limit: 3 },
    active_personas: 25,
    couple_links_active: 1,
    couple_disputes_per_month: 20,
    couple_preps_per_month: 10,
    group_seats_per_room: 5,
    wager_active_stakes: 3,
    wager_max_stake_cents: 10_000,
    roast_feed_posts_per_week: 5,
    persona_earnings_cap_cents_per_month: 50_000,
    contradiction_wall_depth_days: 365,
    context_window_tokens: 128_000,
    mirror_mode: "weekly",
    eulogy_cadence: "quarterly",
    voice_minutes_per_month: 60,
    drill_sergeant_scheduled: 5,
  },
  max: {
    messages_per_day: 1_500,
    council_runs: { period: "day", limit: 20 },
    active_personas: null,
    couple_links_active: 3,
    couple_disputes_per_month: null,
    couple_preps_per_month: null,
    group_seats_per_room: 15,
    wager_active_stakes: 10,
    wager_max_stake_cents: 100_000,
    roast_feed_posts_per_week: 30,
    persona_earnings_cap_cents_per_month: 500_000,
    contradiction_wall_depth_days: null,
    context_window_tokens: 1_000_000,
    mirror_mode: "weekly_and_on_demand",
    eulogy_cadence: "quarterly_and_on_demand",
    voice_minutes_per_month: 300,
    drill_sergeant_scheduled: null,
  },
};

// ----- Wager stake bounds (§9.5.5 + §6.4 CHECK) -----------------------------

export const WAGER_MIN_STAKE_CENTS = 500;
export const WAGER_MAX_STAKE_CENTS_ABSOLUTE = 100_000;

// ----- Persona system bounds (§10.2) ----------------------------------------

export const PERSONA_SYSTEM_PROMPT_MAX_CHARS = 2_000;
export const PERSONA_MARKETPLACE_REVENUE_SHARE = { creator: 0.7, platform: 0.3 } as const;
