import { redirect } from "next/navigation";
import Link from "next/link";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { maxSeatsForTier } from "@/lib/groups";
import { CreateGroupForm } from "./CreateGroupForm";

// /groups/create — owner picks name, seat count, mediator persona.

export default async function CreateGroupPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const seatCap = maxSeatsForTier(tier);

  if (seatCap === 0) {
    return (
      <main className="mx-auto w-full max-w-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Group rooms are paid</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Free tier doesn&apos;t include group rooms. Pro gets you 5 seats per
          room; Max gets 15.
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

  // Eligible mediator personas — anything in 'mediate' or 'council', approved
  // and publicly visible. Default to the_therapist if present.
  const { data: personasRaw } = await supabase
    .from("personas")
    .select("slug, name, category")
    .in("category", ["mediate", "council"])
    .in("visibility", ["official", "public"])
    .eq("moderation_status", "approved")
    .order("category", { ascending: true });
  const personas = (personasRaw ?? []) as Array<{ slug: string; name: string; category: string }>;

  return (
    <main className="mx-auto w-full max-w-xl p-6">
      <Link href="/groups" className="text-sm text-muted-foreground hover:underline">
        ← Groups
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">New group room</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Pick the size, pick the mediator, share the invite link.
        Up to {seatCap} seats on your {tier} tier.
      </p>
      <div className="mt-6">
        <CreateGroupForm seatCap={seatCap} personas={personas} />
      </div>
    </main>
  );
}
