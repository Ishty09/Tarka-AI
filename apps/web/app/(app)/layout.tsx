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

  const [acknowledged, locale, convRes] = await Promise.all([
    hasAcknowledgedAiDisclosure(),
    getLocale(),
    supabase
      .from("conversations")
      .select("id, title, mode, updated_at, archived, persona:personas(name)")
      .eq("user_id", user.id)
      .eq("archived", false)
      .order("updated_at", { ascending: false })
      .limit(80),
  ]);

  const conversations: ConversationSummary[] = (convRes.data ?? []).map((c) => {
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
