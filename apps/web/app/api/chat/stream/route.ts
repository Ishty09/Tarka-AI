import { NextResponse, type NextRequest } from "next/server";
import { chatStreamRequestSchema } from "@quarrel/shared/schemas";
import { createServerSupabase } from "@/lib/supabase/server";
import { serverEnv } from "@/lib/env";

// Web→worker chat-stream proxy (§8.3).
//
// Responsibilities at this layer:
//   1. Authenticate the request from the user's Supabase session cookie.
//   2. Validate the body against the shared zod schema (defense in depth —
//      the worker validates too, but cheap to reject early).
//   3. Forward to workers POST /chat/stream with WORKERS_INTERNAL_SECRET
//      and an X-User-Id header. apps/web is the trust boundary.
//   4. Pipe the SSE stream back to the client unchanged.
//
// What this layer does NOT do: it never calls the LLM directly (§1.4) and
// never reads the service-role key (§1.3). Workers owns both.

export const runtime = "nodejs";
// Force dynamic — caching a streaming POST would be catastrophic.
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  // ----- Auth ----------------------------------------------------------------
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  // ----- Worker secret -------------------------------------------------------
  if (!serverEnv.WORKERS_INTERNAL_SECRET) {
    return NextResponse.json(
      { error: "workers_internal_secret_unset" },
      { status: 503 },
    );
  }

  // ----- Body validation -----------------------------------------------------
  let rawBody: unknown;
  try {
    rawBody = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const parsed = chatStreamRequestSchema.safeParse(rawBody);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid_body", issues: parsed.error.issues },
      { status: 400 },
    );
  }

  // ----- Forward to workers --------------------------------------------------
  const upstream = await fetch(`${serverEnv.WORKERS_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
      "x-user-id": user.id,
    },
    body: JSON.stringify(parsed.data),
    // Stream response — Next must not buffer.
    cache: "no-store",
  });

  if (!upstream.body) {
    return NextResponse.json({ error: "upstream_no_body" }, { status: 502 });
  }

  // Preserve the worker's status (200/429/403/404) and content-type so the
  // client can branch on quota_exceeded etc.
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "text/event-stream",
      "cache-control": "no-cache, no-transform",
      // Vercel buffers responses by default; the X-Accel-Buffering hint
      // disables it on the proxy layer.
      "x-accel-buffering": "no",
    },
  });
}
