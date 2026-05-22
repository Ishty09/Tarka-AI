// Re-export the canonical event list so app callers don't reach across
// packages just for the type (CLAUDE.md §27 step 61).

export {
  ANALYTICS_EVENTS,
  type AnalyticsEvent,
} from "@quarrel/shared/analytics";

// Common context fields per §20. Helpers merge this with per-event props
// before shipping to Umami.
export interface AnalyticsContext {
  /** Hashed user_id (never the raw uuid). */
  user_id?: string;
  tier?: "free" | "pro" | "max";
  locale?: string;
}
