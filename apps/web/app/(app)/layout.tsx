import { getLocale } from "next-intl/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { hasAcknowledgedAiDisclosure } from "@/lib/eu-ai-act";
import { EuAiActModal } from "./_components/EuAiActModal";

// Shared chrome for every (app)/* page. Auth is enforced upstream by
// middleware.ts; this layout adds a small nav strip so signed-in users see
// who they are and can sign out. Onboarding-incomplete users are bounced
// here — their profile row exists but onboarding_completed_at is null, so
// any (app) hit redirects to /onboarding to finish setup.
//
// EU AI Act Article 50 first-run modal mounts here so the disclosure shows
// on every authenticated entry point — chat, tools, personas, etc. — until
// the visitor acknowledges it for this device (§27 step 55).

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

  const [acknowledged, locale] = await Promise.all([
    hasAcknowledgedAiDisclosure(),
    getLocale(),
  ]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-4">
          <Link href="/chat" className="font-semibold tracking-tight">Quarrel</Link>
          <nav className="hidden gap-3 text-sm text-muted-foreground md:flex">
            <Link href="/chat" className="hover:text-foreground">Chat</Link>
            <Link href="/personas" className="hover:text-foreground">Personas</Link>
            <Link href="/contradictions" className="hover:text-foreground">Contradictions</Link>
            <Link href="/wagers" className="hover:text-foreground">Wagers</Link>
            <Link href="/settings" className="hover:text-foreground">Settings</Link>
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">@{profile.username}</span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs uppercase tracking-wide">
            {profile.tier}
          </span>
          <form action="/auth/signout" method="post">
            <button
              type="submit"
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Sign out
            </button>
          </form>
        </div>
      </header>
      <div className="flex-1">{children}</div>
      <EuAiActModal show={!acknowledged} locale={locale} />
    </div>
  );
}
