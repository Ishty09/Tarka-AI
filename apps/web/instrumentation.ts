// Next 15 instrumentation hook for Sentry server + edge runtimes
// (CLAUDE.md §27 step 60). The client init lives in sentry.client.config.ts
// and is picked up by withSentryConfig.

import * as Sentry from "@sentry/nextjs";

export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
