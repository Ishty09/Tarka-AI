import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { createServerSupabase } from "@/lib/supabase/server";
import { serverEnv } from "@/lib/env";

// Roast feed submission (§9.2.5). Flow per turn:
//   1. Verify the user owns the message they're sharing.
//   2. Check the roast-feed quota for the day (§8.1).
//   3. Call workers /tools/moderate with the roast text.
//   4. If approve  → insert with moderation_status='approved' + visibility=chosen
//      If flag     → insert with moderation_status='flagged' + visibility='unlisted'
//      If reject   → 422 to the user
//   5. Increment the quota counter on success.
//
// Step 31's moderation service defaults to 'flag' on any classifier
// failure, so an outage doesn't silently leak content.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const bodySchema = z.object({
  message_id: z.coerce.number().int().positive(),
  caption: z.string().max(280).optional(),
  visibility: z.enum(["public", "unlisted"]).default("public"),
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
  const { message_id, caption, visibility } = parsed.data;

  // ----- Verify message ownership ------------------------------------------
  const { data: message } = await supabase
    .from("messages")
    .select("id, role, content, conversation_id, conversation:conversations!conversation_id(user_id)")
    .eq("id", message_id)
    .maybeSingle();
  if (!message) {
    return NextResponse.json({ error: "message_not_found" }, { status: 404 });
  }
  if (message.role !== "assistant") {
    return NextResponse.json({ error: "not_an_assistant_message" }, { status: 400 });
  }
  const convo = Array.isArray(message.conversation) ? message.conversation[0] : message.conversation;
  if (!convo || convo.user_id !== user.id) {
    return NextResponse.json({ error: "not_message_owner" }, { status: 403 });
  }

  // ----- Quota check via workers (single source of truth) ------------------
  // Defer to the worker route below — but since the workers don't expose a
  // dedicated feed-quota endpoint, we'd round-trip just for state. Cheaper
  // to read usage_quotas directly via the user's authenticated client.
  const today = new Date().toISOString().slice(0, 10);
  const { data: quotaRow } = await supabase
    .from("usage_quotas")
    .select("roast_feed_posts_used")
    .eq("user_id", user.id)
    .eq("period_start", today)
    .maybeSingle();
  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier = profile?.tier ?? "free";
  const limits: Record<string, number> = { free: 0, pro: 1, max: 5 };
  const limit = limits[tier] ?? 0;
  const used = quotaRow?.roast_feed_posts_used ?? 0;
  if (used >= limit) {
    return NextResponse.json(
      {
        error: "quota_exceeded",
        tier,
        limit,
        used,
        upgrade_url: "/pricing",
      },
      { status: 429 },
    );
  }

  // ----- Moderate via workers ----------------------------------------------
  const modRes = await fetch(`${serverEnv.WORKERS_URL}/tools/moderate`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
      "x-user-id": user.id,
    },
    body: JSON.stringify({ content: message.content, kind: "roast_feed_post" }),
    cache: "no-store",
  });
  if (!modRes.ok) {
    return NextResponse.json(
      { error: "moderation_failed", status: modRes.status },
      { status: 502 },
    );
  }
  const moderation = (await modRes.json()) as {
    action: "approve" | "reject" | "flag";
    reason: string;
    categories: string[];
  };

  if (moderation.action === "reject") {
    return NextResponse.json(
      { error: "moderation_rejected", reason: moderation.reason, categories: moderation.categories },
      { status: 422 },
    );
  }

  // ----- Insert post -------------------------------------------------------
  const insertVisibility = moderation.action === "flag" ? "unlisted" : visibility;
  const insertStatus = moderation.action === "flag" ? "flagged" : "approved";

  const { data: postRow, error: insertErr } = await supabase
    .from("roast_feed_posts")
    .insert({
      user_id: user.id,
      conversation_id: message.conversation_id,
      message_id: message.id,
      caption: caption ?? null,
      visibility: insertVisibility,
      moderation_status: insertStatus,
      is_safe: moderation.action === "approve",
    })
    .select("id, visibility, moderation_status")
    .maybeSingle();

  if (insertErr || !postRow) {
    return NextResponse.json(
      { error: "insert_failed", reason: insertErr?.message ?? "unknown" },
      { status: 502 },
    );
  }

  // ----- Bump quota --------------------------------------------------------
  await supabase
    .from("usage_quotas")
    .upsert(
      {
        user_id: user.id,
        period_start: today,
        roast_feed_posts_used: used + 1,
      },
      { onConflict: "user_id,period_start" },
    );

  return NextResponse.json({
    ok: true,
    post: postRow,
    moderation: {
      action: moderation.action,
      reason: moderation.reason,
      categories: moderation.categories,
    },
  });
}
