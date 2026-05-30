import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase/server";

// Targeted bisect of the conversations read failure. Hits the table
// six ways to identify exactly which layer (auth, user filter, boolean
// filter, FK embed, or head:count syntax) is the actual blocker.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface ProbeOutcome {
  ok: boolean;
  count: number;
  error: string | null;
  error_code?: string;
  error_hint?: string;
}

function summarize(
  res: { data?: unknown[] | null; error?: { message?: string; code?: string; hint?: string } | null; count?: number | null },
): ProbeOutcome {
  return {
    ok: !res.error,
    count: res.data?.length ?? res.count ?? 0,
    error: res.error?.message ?? null,
    error_code: res.error?.code,
    error_hint: res.error?.hint,
  };
}

export async function GET() {
  const supabase = await createServerSupabase();
  const { data: { user }, error: authError } = await supabase.auth.getUser();
  if (authError || !user) {
    return NextResponse.json(
      { ok: false, error: "unauthenticated", auth_error: authError?.message },
      { status: 401 },
    );
  }

  // Sanity: profile read. The layout already does this and succeeds —
  // establishes that the supabase client has a working auth context.
  const sanityProfile = summarize(
    await supabase.from("profiles").select("id").eq("id", user.id).limit(1),
  );

  // Probe 1: bare SELECT — no filters, no embed.
  const probe1Bare = summarize(
    await supabase.from("conversations").select("id").limit(50),
  );

  // Probe 2: filter by user_id only.
  const probe2UserId = summarize(
    await supabase.from("conversations").select("id").eq("user_id", user.id).limit(50),
  );

  // Probe 3: add the boolean filter the way /chat does it.
  const probe3EqArchivedFalse = summarize(
    await supabase
      .from("conversations")
      .select("id")
      .eq("user_id", user.id)
      .eq("archived", false)
      .limit(50),
  );

  // Probe 4: same filter but with .is() — PostgREST's canonical bool op.
  const probe4IsArchivedFalse = summarize(
    await supabase
      .from("conversations")
      .select("id")
      .eq("user_id", user.id)
      .is("archived", false)
      .limit(50),
  );

  // Probe 5: add the personas embed.
  const probe5WithEmbed = summarize(
    await supabase
      .from("conversations")
      .select("id, persona:personas(slug, name)")
      .eq("user_id", user.id)
      .eq("archived", false)
      .limit(5),
  );

  // Probe 6: head:true,count:exact (the shape my first /diagnostics used).
  const probe6HeadCount = summarize(
    await supabase
      .from("conversations")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id),
  );

  return NextResponse.json({
    user_id: user.id,
    auth_email: user.email,
    sanity_profile: sanityProfile,
    probe1_bare_conversations: probe1Bare,
    probe2_filter_user_id: probe2UserId,
    probe3_eq_archived_false: probe3EqArchivedFalse,
    probe4_is_archived_false: probe4IsArchivedFalse,
    probe5_with_personas_embed: probe5WithEmbed,
    probe6_head_count_exact: probe6HeadCount,
    expected_total_from_db: 24,
  });
}
