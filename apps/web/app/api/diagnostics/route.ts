import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase/server";
import { serverEnv } from "@/lib/env";

// Single-shot system health snapshot. Hit it as a signed-in user;
// copy/paste the JSON to support if something looks wrong end-to-end.
// Every check is wrapped in its own try so one broken probe doesn't
// hide the rest.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface CheckResult {
  ok: boolean;
  detail?: unknown;
  error?: string;
}

async function safe(fn: () => Promise<CheckResult>): Promise<CheckResult> {
  try {
    return await fn();
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Unknown error",
    };
  }
}

export async function GET() {
  const supabase = await createServerSupabase();
  const { data: { user }, error: authError } = await supabase.auth.getUser();
  if (authError || !user) {
    return NextResponse.json(
      {
        ok: false,
        error: "unauthenticated",
        hint: "Sign in first, then hit this URL.",
      },
      { status: 401 },
    );
  }

  // ----- Web build marker (Vercel deployment commit) ----------------------
  const webDeployment = {
    commit: process.env.VERCEL_GIT_COMMIT_SHA ?? "(local-dev)",
    commit_short: (process.env.VERCEL_GIT_COMMIT_SHA ?? "(local)").slice(0, 7),
    deployed_url: process.env.VERCEL_URL ?? "(local)",
    deployed_branch: process.env.VERCEL_GIT_COMMIT_REF ?? "(local)",
  };

  // ----- Workers reachable + build marker --------------------------------
  const workersCheck: CheckResult = await safe(async () => {
    if (!serverEnv.WORKERS_URL) {
      return { ok: false, error: "WORKERS_URL not set" };
    }
    const res = await fetch(`${serverEnv.WORKERS_URL}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    });
    if (!res.ok) {
      return { ok: false, error: `workers /health returned ${res.status}` };
    }
    const body = await res.json();
    return { ok: true, detail: body };
  });

  // ----- DB: is the new couples-invite RLS policy installed? -------------
  const rlsCheck: CheckResult = await safe(async () => {
    // pg_policies is queryable by authenticated users via supabase by
    // default. If it's not, the .from() call will error and the
    // wrapped catch will surface it.
    const res = await supabase
      .from("pg_policies" as never)
      .select("policyname, tablename")
      .eq("tablename", "couple_links")
      .eq("policyname", "couple_links_pending_invite_lookup");
    if (res.error) {
      return { ok: false, error: res.error.message, detail: res.error };
    }
    const rows = (res.data as { policyname: string; tablename: string }[]) ?? [];
    return {
      ok: rows.length > 0,
      detail: rows.length > 0
        ? "couple_links_pending_invite_lookup IS installed"
        : "couple_links_pending_invite_lookup is MISSING — run the migration SQL in Supabase Dashboard",
    };
  });

  // ----- Conversations: count + sample row -------------------------------
  const conversationsCheck: CheckResult = await safe(async () => {
    const countRes = await supabase
      .from("conversations")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id);
    if (countRes.error) {
      return { ok: false, error: countRes.error.message };
    }
    const activeCountRes = await supabase
      .from("conversations")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id)
      .eq("archived", false);

    const sampleRes = await supabase
      .from("conversations")
      .select("id, mode, archived, title, created_at, updated_at")
      .eq("user_id", user.id)
      .order("updated_at", { ascending: false })
      .limit(3);

    return {
      ok: true,
      detail: {
        total_for_user: countRes.count ?? 0,
        active_for_user: activeCountRes.count ?? 0,
        sample_recent_three: sampleRes.data ?? [],
      },
    };
  });

  // ----- Messages: have they ever sent any? ------------------------------
  const messagesCheck: CheckResult = await safe(async () => {
    const res = await supabase
      .from("messages")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id);
    if (res.error) return { ok: false, error: res.error.message };
    return { ok: true, detail: { total_user_messages: res.count ?? 0 } };
  });

  return NextResponse.json(
    {
      ok: true,
      generated_at: new Date().toISOString(),
      auth: {
        user_id: user.id,
        email: user.email,
      },
      web: webDeployment,
      workers: workersCheck,
      database: {
        couples_invite_rls: rlsCheck,
      },
      data: {
        conversations: conversationsCheck,
        messages: messagesCheck,
      },
      next_steps: [
        "If workers.detail.build_marker is missing or older than '2026-05-29-council-structured-errors', Coolify hasn't actually redeployed the workers container.",
        "If database.couples_invite_rls.ok is false, the migration SQL was never applied to your prod DB — paste the SQL into Supabase Dashboard SQL Editor.",
        "If data.conversations.detail.active_for_user is 0, you genuinely have no conversations on this signed-in account — either your old chats are under a different auth.users row, or workers persistence failed silently. Try sending a fresh test message.",
      ],
    },
    { status: 200 },
  );
}
