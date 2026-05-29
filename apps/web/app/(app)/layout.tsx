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

  // Sidebar conversation list. Primary path is the
  // get_sidebar_conversations RPC (one round-trip, includes the first
  // user message excerpt for fallback titles). If the RPC errors —
  // missing function on prod, RLS misconfig, anything — we fall back
  // to a direct conversations + personas query so the sidebar still
  // shows chats. The fallback skips the first-message excerpt; titles
  // come from conversations.title which is set on the first turn by
  // the workers route.
  type SidebarRpcRow = {
    id: string;
    title: string | null;
    mode: string;
    updated_at: string;
    archived: boolean;
    persona_name: string | null;
    first_user_message: string | null;
  };

  const [acknowledged, locale, convRes] = await Promise.all([
    hasAcknowledgedAiDisclosure(),
    getLocale(),
    supabase.rpc("get_sidebar_conversations", {
      p_user_id: user.id,
      p_limit: 30,
    }),
  ]);

  let conversations: ConversationSummary[];
  if (convRes.error) {
    console.error("[layout] get_sidebar_conversations failed, falling back", {
      user_id: user.id,
      code: convRes.error.code,
      message: convRes.error.message,
      details: convRes.error.details,
      hint: convRes.error.hint,
    });

    const fallback = await supabase
      .from("conversations")
      .select("id, title, mode, updated_at, archived, personas(name)")
      .eq("user_id", user.id)
      .eq("archived", false)
      .order("updated_at", { ascending: false })
      .limit(30);

    if (fallback.error) {
      console.error("[layout] direct conversations fallback also failed", {
        user_id: user.id,
        code: fallback.error.code,
        message: fallback.error.message,
      });
      conversations = [];
    } else {
      type DirectRow = {
        id: string;
        title: string | null;
        mode: string;
        updated_at: string;
        archived: boolean;
        // PostgREST returns the joined `personas` as either an object
        // or an array depending on the FK direction. Treat both.
        personas: { name: string | null } | { name: string | null }[] | null;
      };
      conversations = (fallback.data as DirectRow[]).map((c) => {
        const personaName = Array.isArray(c.personas)
          ? c.personas[0]?.name ?? null
          : c.personas?.name ?? null;
        return {
          id: c.id,
          title: c.title,
          mode: c.mode,
          updated_at: c.updated_at,
          archived: c.archived,
          persona_name: personaName,
        };
      });
    }
  } else {
    const rows = (convRes.data ?? []) as SidebarRpcRow[];
    conversations = rows.map((c) => ({
      id: c.id,
      title: c.title ?? c.first_user_message ?? null,
      mode: c.mode,
      updated_at: c.updated_at,
      archived: c.archived,
      persona_name: c.persona_name,
    }));
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
