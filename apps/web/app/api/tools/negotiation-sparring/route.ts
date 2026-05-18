import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createServerSupabase } from "@/lib/supabase/server";
import { serverEnv } from "@/lib/env";

// POST /api/tools/negotiation-sparring — starts a session (§9.5.3).
// GET  /api/tools/negotiation-sparring — lists scenarios.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const startSchema = z.object({
  scenario_slug: z.string().min(1).max(80),
});

async function authedFetch(
  upstreamPath: string,
  init: { method: "GET" | "POST"; body?: string },
  request: NextRequest,
): Promise<Response | NextResponse> {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }
  if (!serverEnv.WORKERS_INTERNAL_SECRET) {
    return NextResponse.json(
      { error: "workers_internal_secret_unset" },
      { status: 503 },
    );
  }
  void request; // unused but keeps the signature consistent for future shaping
  const upstream = await fetch(`${serverEnv.WORKERS_URL}${upstreamPath}`, {
    method: init.method,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
      "x-user-id": user.id,
    },
    body: init.body,
    cache: "no-store",
  });
  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}

export async function GET(request: NextRequest) {
  return authedFetch(
    "/tools/negotiation-sparring/scenarios",
    { method: "GET" },
    request,
  );
}

export async function POST(request: NextRequest) {
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const parsed = startSchema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid_body", issues: parsed.error.issues },
      { status: 400 },
    );
  }
  return authedFetch(
    "/tools/negotiation-sparring",
    { method: "POST", body: JSON.stringify(parsed.data) },
    request,
  );
}
