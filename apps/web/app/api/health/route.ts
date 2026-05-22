import { NextResponse } from "next/server";

// Public liveness probe (CLAUDE.md §27 step 63). UptimeRobot pings this on
// 5-minute intervals; a non-200 fires the alert chain documented in
// infra/runbooks/uptimerobot.md.
//
// We intentionally don't dependency-check Supabase / workers here. A DB or
// LiteLLM outage already pages on its own monitor, and chaining them
// turns one outage into multiple pages with confusing causality. This
// endpoint says: "Next.js itself is up and serving."

export const dynamic = "force-static";
export const revalidate = false;

export function GET(): NextResponse {
  return NextResponse.json({
    status: "ok",
    app: "quarrel-web",
    build: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "dev",
  });
}
