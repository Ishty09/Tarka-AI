// Re-exports — client/server callers import from "@/lib/analytics".

export type { AnalyticsContext, AnalyticsEvent } from "./events";
export { ANALYTICS_EVENTS } from "./events";
export { hashUserId, trackServer } from "./server";
// `track` (client) lives at "@/lib/analytics/client" to keep client/server
// boundaries explicit. Don't re-export it here.
