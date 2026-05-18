import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { ROAST_TARGETS } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { serverEnv } from "@/lib/env";

// Web→worker proxy for /tools/roast-my-x (§9.2.2).

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const bodySchema = z.object({
  target: z.enum(ROAST_TARGETS),
  content: z.string().min(20).max(6000),
});

export async function POST(request: NextRequest) {
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

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const parsed = bodySchema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid_body", issues: parsed.error.issues },
      { status: 400 },
    );
  }

  const upstream = await fetch(`${serverEnv.WORKERS_URL}/tools/roast-my-x`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
      "x-user-id": user.id,
    },
    body: JSON.stringify(parsed.data),
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
