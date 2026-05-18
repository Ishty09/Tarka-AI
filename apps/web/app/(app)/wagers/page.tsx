import Link from "next/link";
import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import {
  formatCents,
  maxActiveWagersForTier,
  maxStakeCentsForTier,
} from "@/lib/wagers";

// Wagers list (§9.5.5). Groups by status. Free tier sees an upsell.

type WagerRow = {
  id: string;
  goal: string;
  stake_cents: number;
  currency: string;
  status: string;
  start_at: string;
  end_at: string;
  anti_charity_slug: string;
  anti_charity: { name: string; ideological_tag: string } | { name: string; ideological_tag: string }[] | null;
};

function unwrap<T>(v: T | T[] | null): T | null {
  if (!v) return null;
  return Array.isArray(v) ? v[0] ?? null : v;
}

export default async function WagersPage() {
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
  const maxStake = maxStakeCentsForTier(tier);

  const { data: wagersData } = await supabase
    .from("wagers")
    .select(
      "id, goal, stake_cents, currency, status, start_at, end_at, anti_charity_slug, "
      + "anti_charity:anti_charities!anti_charity_slug(name, ideological_tag)",
    )
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(50);
  const wagers = (wagersData ?? []) as unknown as WagerRow[];

  const active = wagers.filter((w) => w.status === "pending" || w.status === "active");
  const resolved = wagers.filter((w) => !["pending", "active"].includes(w.status));

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Wagers</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Put real money on the line. If you miss the goal, your stake goes
            to a cause you actively dislike — that&apos;s the point.
          </p>
        </div>
        {maxActive > 0 ? (
          <Link
            href="/wagers/create"
            className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            New wager
          </Link>
        ) : (
          <Link
            href="/pricing"
            className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            Upgrade to wager
          </Link>
        )}
      </div>

      <p className="mt-2 text-xs text-muted-foreground">
        Tier: {tier} ·{" "}
        {maxActive === 0
          ? "no wagers"
          : `up to ${maxActive} active, max stake ${formatCents(maxStake)}`}
      </p>

      <Section
        title="Active"
        wagers={active}
        emptyHint={maxActive === 0 ? null : "No active wagers."}
      />
      <Section
        title="Resolved"
        wagers={resolved}
        emptyHint="No resolved wagers yet."
      />

      {wagers.length === 0 && maxActive > 0 && (
        <p className="mt-10 text-sm text-muted-foreground">
          Pick a goal, pick a deadline, pick the cause you most want NOT to
          fund. Then deliver.
        </p>
      )}
    </main>
  );
}

function Section({
  title,
  wagers,
  emptyHint,
}: {
  title: string;
  wagers: WagerRow[];
  emptyHint: string | null;
}) {
  if (wagers.length === 0 && !emptyHint) return null;
  return (
    <section className="mt-8">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      {wagers.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">{emptyHint}</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {wagers.map((w) => {
            const charity = unwrap(w.anti_charity);
            return (
              <li key={w.id}>
                <Link
                  href={`/wagers/${w.id}`}
                  className="flex items-center justify-between rounded-md border border-input bg-background px-4 py-3 text-sm shadow-sm hover:bg-accent"
                >
                  <div className="flex flex-col">
                    <span className="font-medium">{w.goal}</span>
                    <span className="text-xs text-muted-foreground">
                      {formatCents(w.stake_cents, w.currency.toUpperCase())} → {charity?.name ?? w.anti_charity_slug}
                      {" · "}
                      {new Date(w.start_at).toLocaleDateString()} → {new Date(w.end_at).toLocaleDateString()}
                    </span>
                  </div>
                  <StatusBadge status={w.status} />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tone: Record<string, string> = {
    pending: "border-amber-500/40 bg-amber-500/10 text-amber-700",
    active: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700",
    succeeded: "border-emerald-500/30 bg-emerald-500/15 text-emerald-700",
    failed: "border-red-500/40 bg-red-500/10 text-red-700",
    disputed: "border-amber-500/40 bg-amber-500/15 text-amber-700",
    refunded: "border-input bg-muted/30 text-muted-foreground",
  };
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${tone[status] ?? "border-input bg-muted/30 text-muted-foreground"}`}
    >
      {status}
    </span>
  );
}
