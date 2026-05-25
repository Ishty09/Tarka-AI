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

  // Sidebar uses the get_sidebar_conversations RPC instead of two
  // queries (conversations + a full message scan). The RPC returns
  // one row per conversation with the first user message excerpt
  // baked in via a substring(..for 200) so we avoid pulling raw
  // chat content into the layout fetch on every navigation.
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

  const rows = (convRes.data ?? []) as SidebarRpcRow[];
  const conversations: ConversationSummary[] = rows.map((c) => ({
    id: c.id,
    title: c.title ?? c.first_user_message ?? null,
    mode: c.mode,
    updated_at: c.updated_at,
    archived: c.archived,
    persona_name: c.persona_name,
  }));

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
