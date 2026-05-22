"use client";

// Client-side Umami event helper (CLAUDE.md §20, §27 step 61).
//
// Calls into the window.umami namespace exposed by the Umami tracking
// script — see apps/web/app/layout.tsx for the <Script /> that injects
// it. Each call is a fire-and-forget; if the script hasn't loaded yet
// (initial paint, ad-blocker) we silently drop the event rather than
// blocking the UI.

import type { AnalyticsEvent } from "./events";

declare global {
  interface Window {
    umami?: {
      track: (event: string, data?: Record<string, unknown>) => void;
    };
  }
}

export function track(
  event: AnalyticsEvent,
  data?: Record<string, unknown>,
): void {
  if (typeof window === "undefined") return;
  try {
    window.umami?.track(event, data);
  } catch {
    // Telemetry must never throw. Swallow.
  }
}
