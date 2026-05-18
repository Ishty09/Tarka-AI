import { redirect } from "next/navigation";
import Link from "next/link";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import {
  formatCents,
  maxActiveWagersForTier,
  maxStakeCentsForTier,
  minStakeCents,
  polarEnabled,
} from "@/lib/wagers";
import { CreateWagerForm } from "./CreateWagerForm";

interface AntiCharityRow {
  slug: string;
  name: string;
  description: string;
  ideological_tag: string;
}

export default async function CreateWagerPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const maxActive = maxActiveWagersForTier(tier);

  if (maxActive === 0) {
    return (
      <main className="mx-auto w-full max-w-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Wagers are paid</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Free tier doesn&apos;t include wagers. Pro lets you stake up to $100
          per wager; Max goes up to $1000.
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

  const { data: antiCharitiesData } = await supabase
    .from("anti_charities")
    .select("slug, name, description, ideological_tag")
    .eq("active", true)
    .order("name", { ascending: true });
  const antiCharities = (antiCharitiesData ?? []) as AntiCharityRow[];

  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <Link href="/wagers" className="text-sm text-muted-foreground hover:underline">
        ← Wagers
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">New wager</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Stake from {formatCents(minStakeCents())} up to{" "}
        {formatCents(maxStakeCentsForTier(tier))} on your {tier} tier.{" "}
        {polarEnabled()
          ? "Funds are held by Polar.sh and only captured if you fail."
          : "Payments are stubbed during pre-launch; this is a dry run."}
      </p>
      <div className="mt-6">
        <CreateWagerForm
          tier={tier}
          minStake={minStakeCents()}
          maxStake={maxStakeCentsForTier(tier)}
          antiCharities={antiCharities}
          polarEnabled={polarEnabled()}
        />
      </div>
    </main>
  );
}
