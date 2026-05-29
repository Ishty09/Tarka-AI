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
      error: err instanceof Error
        ? err.message || err.toString() || "thrown empty Error"
        : `non-Error thrown: ${String(err)}`,
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
    const body: Record<string, unknown> = await res.json();
    const hasMarker =
      typeof body.build_marker === "string" && body.build_marker.length > 0;
    return {
      ok: hasMarker,
      detail: {
        body,
        verdict: hasMarker
          ? `build_marker present — workers ARE running latest code: ${String(body.build_marker)}`
          : "build_marker MISSING — Coolify hasn't pushed the new container. Redeploy workers from the Coolify dashboard.",
      },
    };
  });

  // ----- DB: can we query couple_links at all (smoke test)? -------------
  // pg_policies lives in pg_catalog and isn't queryable through PostgREST,
  // so we can't introspect the policy list from here. Instead: do a
  // controlled lookup with a code that can't exist. We expect 0 rows
  // either way. The check is mostly that the table is reachable.
  const couplesTableCheck: CheckResult = await safe(async () => {
    const res = await supabase
      .from("couple_links")
      .select("id")
      .eq("invite_code", "DIAGNOSTIC-PROBE-INVALID-CODE")
      .limit(1);
    if (res.error) {
      return {
        ok: false,
        error: res.error.message,
        detail: {
          code: res.error.code,
          hint: res.error.hint,
          note: "couple_links table not reachable via PostgREST — check RLS / grants.",
        },
      };
    }
    return {
      ok: true,
      detail: {
        rows_returned_for_fake_code: (res.data ?? []).length,
        note: "Table reachable. Manual RLS-policy check below.",
      },
    };
  });

  // ----- Conversations: count + sample row (no head/count tricks) -------
  const conversationsCheck: CheckResult = await safe(async () => {
    const allRes = await supabase
      .from("conversations")
      .select("id, mode, archived, title, created_at, updated_at")
      .eq("user_id", user.id)
      .order("updated_at", { ascending: false })
      .limit(50);
    if (allRes.error) {
      return {
        ok: false,
        error: allRes.error.message,
        detail: { code: allRes.error.code, hint: allRes.error.hint },
      };
    }
    const all = allRes.data ?? [];
    const active = all.filter((r) => r.archived === false);
    const archived = all.filter((r) => r.archived === true);
    return {
      ok: true,
      detail: {
        total_for_user: all.length,
        active_for_user: active.length,
        archived_for_user: archived.length,
        sample_recent_three: all.slice(0, 3),
      },
    };
  });

  // ----- Messages: have they ever sent any? ------------------------------
  const messagesCheck: CheckResult = await safe(async () => {
    const res = await supabase
      .from("messages")
      .select("id, role, created_at")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .limit(50);
    if (res.error) {
      return {
        ok: false,
        error: res.error.message,
        detail: { code: res.error.code, hint: res.error.hint },
      };
    }
    const rows = res.data ?? [];
    return {
      ok: true,
      detail: {
        total_user_messages: rows.length,
        most_recent: rows[0]?.created_at ?? null,
      },
    };
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
        couples_table_reachable: couplesTableCheck,
        couples_rls_policy_check: {
          ok: null,
          detail:
            "pg_policies cannot be queried via PostgREST. Run this in Supabase Dashboard → SQL Editor:\n" +
            "select policyname from pg_policies where tablename = 'couple_links';\n" +
            "Look for 'couple_links_pending_invite_lookup' in the results. If missing, the migration SQL wasn't applied.",
        },
      },
      data: {
        conversations: conversationsCheck,
        messages: messagesCheck,
      },
      next_steps: [
        "If workers.detail.body.build_marker is missing or older than '2026-05-29-council-structured-errors', Coolify hasn't actually redeployed the workers container. THIS IS LIKELY THE PRIMARY BLOCKER.",
        "If data.conversations.detail.total_for_user > 0 but active_for_user is 0, all your chats are archived (unarchive at /chat?show=archived).",
        "If data.conversations.detail.total_for_user is 0 AND workers don't have the marker → chats can't persist because workers are running old code. Fix workers first, THEN send a test message.",
      ],
    },
    { status: 200 },
  );
}
