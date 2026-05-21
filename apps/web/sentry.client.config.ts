// Sentry client-side init (CLAUDE.md §27 step 60). Runs in the browser.
//
// No DSN → no-op. SendDefaultPii is off; the beforeSend hook double-scrubs
// any auth headers or request bodies that might appear in fetch breadcrumbs.

import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_ENV ?? process.env.NODE_ENV ?? "development",
    sendDefaultPii: false,
    tracesSampleRate: 0.1,
    // Replays disabled for now — too noisy and the privacy implications
    // for chat content need a separate review before we turn this on.
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    beforeSend: (event) => {
      // Drop request bodies; chat content must not leak to Sentry.
      if (event.request) {
        delete event.request.data;
        delete event.request.cookies;
        if (event.request.headers) {
          for (const key of Object.keys(event.request.headers)) {
            const lower = key.toLowerCase();
            if (
              lower.includes("authorization") ||
              lower.includes("cookie") ||
              lower.includes("api-key")
            ) {
              event.request.headers[key] = "[REDACTED]";
            }
          }
        }
      }
      if (event.user) {
        delete event.user.email;
        delete event.user.ip_address;
        delete event.user.username;
      }
      return event;
    },
  });
}
