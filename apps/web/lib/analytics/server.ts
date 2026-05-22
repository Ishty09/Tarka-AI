// Server-side Umami event helper (CLAUDE.md §20, §27 step 61).
//
// POSTs to Umami's /api/send collect endpoint. The endpoint accepts
// anonymous events as long as the websiteId matches a registered site,
// which is fine for first-party server-side firings.
//
// Hashing: we never push the raw Supabase uuid into analytics. The
// `hashUserId` helper turns it into a stable per-deployment fingerprint
// — same uuid yields the same hash across requests, no cross-deployment
// linkability.

import { createHash } from "node:crypto";
import type { AnalyticsContext, AnalyticsEvent } from "./events";

const SCRIPT_PATH_SUFFIX = "/script.js";

function collectEndpoint(): string | null {
  const scriptUrl = process.env.NEXT_PUBLIC_UMAMI_SCRIPT_URL;
  if (!scriptUrl) return null;
  if (scriptUrl.endsWith(SCRIPT_PATH_SUFFIX)) {
    return `${scriptUrl.slice(0, -SCRIPT_PATH_SUFFIX.length)}/api/send`;
  }
  // Defensive — if the env var was set to a base path instead.
  return `${scriptUrl.replace(/\/+$/, "")}/api/send`;
}

export function hashUserId(userId: string | undefined): string | undefined {
  if (!userId) return undefined;
  return createHash("sha256")
    .update(userId)
    .digest("hex")
    .slice(0, 16);
}

interface TrackOptions {
  context?: AnalyticsContext;
  /** Hostname override; defaults to NEXT_PUBLIC_APP_URL's hostname. */
  hostname?: string;
  userAgent?: string;
  /** Per-request fetch override for tests. */
  fetchImpl?: typeof fetch;
}

/**
 * Fire an event server-side. Best-effort: any network error is swallowed.
 * Caller is expected to await but tolerating a failure is the point.
 */
export async function trackServer(
  event: AnalyticsEvent,
  data: Record<string, unknown> = {},
  opts: TrackOptions = {},
): Promise<void> {
  const websiteId = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID;
  const endpoint = collectEndpoint();
  if (!websiteId || !endpoint) return;

  let hostname = opts.hostname;
  if (!hostname) {
    const appUrl = process.env.NEXT_PUBLIC_APP_URL;
    if (appUrl) {
      try {
        hostname = new URL(appUrl).hostname;
      } catch {
        hostname = undefined;
      }
    }
  }

  const context = opts.context ?? {};
  const merged = { ...data, ...context };

  const body = {
    type: "event",
    payload: {
      website: websiteId,
      name: event,
      data: merged,
      hostname,
      language: context.locale,
      url: data.url ?? "/",
    },
  };

  const fetchImpl = opts.fetchImpl ?? fetch;
  try {
    await fetchImpl(endpoint, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "user-agent": opts.userAgent ?? "Quarrel/1.0 (+server)",
      },
      body: JSON.stringify(body),
    });
  } catch {
    // Telemetry never throws into business logic.
  }
}
