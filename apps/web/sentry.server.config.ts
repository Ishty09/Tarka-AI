// Sentry server-side init (CLAUDE.md §27 step 60). Runs in the Node runtime
// of Next.js — server actions, API routes, RSC payloads.

import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN ?? process.env.SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV ?? "development",
    sendDefaultPii: false,
    tracesSampleRate: 0.1,
    beforeSend: (event) => {
      if (event.request) {
        delete event.request.data;
        delete event.request.cookies;
        if (event.request.headers) {
          for (const key of Object.keys(event.request.headers)) {
            const lower = key.toLowerCase();
            if (
              lower.includes("authorization") ||
              lower.includes("cookie") ||
              lower.includes("api-key") ||
              lower.includes("service-role")
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
