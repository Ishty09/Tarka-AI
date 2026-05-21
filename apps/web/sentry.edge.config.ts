// Sentry edge runtime init (CLAUDE.md §27 step 60).
//
// Runs in the Vercel Edge / Middleware runtime — limited Node API surface, so
// we keep this slim. The scrubber mirrors the server one without the cookie
// and request.data handling that edge doesn't reliably expose.

import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN ?? process.env.SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV ?? "development",
    sendDefaultPii: false,
    tracesSampleRate: 0.05,
    beforeSend: (event) => {
      if (event.request?.headers) {
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
      if (event.user) {
        delete event.user.email;
        delete event.user.ip_address;
        delete event.user.username;
      }
      return event;
    },
  });
}
