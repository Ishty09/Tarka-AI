import { getLocale } from "next-intl/server";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { hasAcknowledgedAiDisclosure } from "@/lib/eu-ai-act";
import { AppShell } from "./_components/AppShell";
import { EuAiActModal } from "./_components/EuAiActModal";
import type { ConversationSummary } from "./_components/Sidebar";

// Shared chrome for every (app)/* page. Auth + onboarding gate up top,
// then renders the sidebar shell. The sidebar lists the user's recent
// conversations so jumping between chats is one click, not a trip back
// through /chat. Mobile uses a drawer; desktop keeps the sidebar pinned.
//
// EU AI Act Article 50 first-run modal mounts here so the disclosure
// shows on every authenticated entry point until acknowledged (§27 step
// 55).

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("username, display_name, onboarding_completed_at, tier")
    .eq("id", user.id)
    .maybeSingle();

  if (!profile?.onboarding_completed_at) redirect("/onboarding");

  // Sidebar conversation list. The /chat page already runs a direct
  // conversations + personas select that's been working — we mirror
  // that EXACT query here so the sidebar never disagrees with /chat
  // about what conversations exist. (Earlier the layout used an RPC
  // which was returning empty for some users — root cause unknown,
  // but bypassing the RPC removes a moving part.)
  type DirectRow = {
    id: string;
    title: string | null;
    mode: string;
    updated_at: string;
    archived: boolean;
    // PostgREST returns the joined `personas` as either an object or
    // an array depending on the FK direction. Treat both.
    persona:
      | { slug: string | null; name: string | null }
      | { slug: string | null; name: string | null }[]
      | null;
  };

  const [acknowledged, locale, convRes] = await Promise.all([
    hasAcknowledgedAiDisclosure(),
    getLocale(),
    supabase
      .from("conversations")
      .select("id, title, mode, updated_at, archived, persona:personas(slug, name)")
      .eq("user_id", user.id)
      .eq("archived", false)
      .order("updated_at", { ascending: false })
      .limit(30),
  ]);

  let conversations: ConversationSummary[];
  if (convRes.error) {
    console.error("[layout] conversations query failed", {
      user_id: user.id,
      code: convRes.error.code,
      message: convRes.error.message,
      details: convRes.error.details,
      hint: convRes.error.hint,
    });
    conversations = [];
  } else {
    const rows = (convRes.data ?? []) as DirectRow[];
    // Always log the count so a "sidebar empty" support thread has the
    // concrete number, not just the empty render.
    console.log("[layout] sidebar conversations", {
      user_id: user.id,
      count: rows.length,
    });
    conversations = rows.map((c) => {
      const persona = Array.isArray(c.persona) ? c.persona[0] : c.persona;
      return {
        id: c.id,
        title: c.title,
        mode: c.mode,
        updated_at: c.updated_at,
        archived: c.archived,
        persona_name: persona?.name ?? null,
      };
    });
  }

  return (
    <>
      <AppShell
        conversations={conversations}
        username={profile.username}
        tier={profile.tier}
      >
        {children}
      </AppShell>
      <EuAiActModal show={!acknowledged} locale={locale} />
    </>
  );
}
