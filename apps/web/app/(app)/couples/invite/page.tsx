import { redirect } from "next/navigation";
import Link from "next/link";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { activeCoupleLimitFor } from "@/lib/couples";
import { InviteForm } from "./InviteForm";

// /couples/invite — generate an invite code. The actual link copy
// happens client-side from InviteForm once the action returns.

export default async function CouplesInvitePage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const limit = activeCoupleLimitFor(tier);

  if (limit === 0) {
    return (
      <main className="mx-auto w-full max-w-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Couples mode is paid</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Free tier doesn&apos;t include couples mode. Pro gets you one active
          link, Max gets three.
        </p>
        <Link
          href="/pricing"
          className="mt-4 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          See pricing
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-xl p-6">
      <Link href="/couples" className="text-sm text-muted-foreground hover:underline">
        ← Couples
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Invite your partner</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        We generate a one-time invite link. Send it over whichever channel you
        already use (WhatsApp, iMessage, Signal — whatever). It expires in 7
        days; if they don&apos;t accept by then, you can re-issue.
      </p>
      <div className="mt-6">
        <InviteForm />
      </div>
    </main>
  );
}
