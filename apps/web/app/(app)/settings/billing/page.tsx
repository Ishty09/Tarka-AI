import { redirect } from "next/navigation";
import Link from "next/link";
import { TIER_LIMITS, type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { polarEnabled } from "@/lib/wagers";
import { SettingsSection } from "../_components/SettingsSection";

// §12.4 — Billing. Surfaces current tier, the active Polar/RC subscription,
// and the per-tier limits the user is hitting. The "Manage" CTA hands off to
// Polar's hosted portal (set POLAR_MANAGE_URL). Invoice history is also a
// Polar surface — we don't try to mirror invoices into our DB.

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

export default async function BillingPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const [{ data: profile }, { data: subs }] = await Promise.all([
    supabase.from("profiles").select("tier, tier_source").eq("id", user.id).maybeSingle(),
    supabase
      .from("subscriptions")
      .select(
        "id, tier, status, source, external_subscription_id, current_period_start, current_period_end, cancel_at_period_end, canceled_at",
      )
      .eq("user_id", user.id)
      .order("current_period_end", { ascending: false })
      .limit(5),
  ]);
  if (!profile) redirect("/onboarding");

  const tier: Tier = (profile.tier as Tier) ?? "free";
  const limits = TIER_LIMITS[tier];
  const active = (subs ?? []).find((s) => s.status === "active" || s.status === "trialing");
  const manageUrl = process.env.POLAR_MANAGE_URL ?? null;
  const upgradeReady = polarEnabled() && tier === "free";

  return (
    <div className="flex flex-col gap-6">
      <SettingsSection
        title="Current plan"
        description="All features live on every tier; only limits differ."
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-2xl font-semibold tracking-tight uppercase">{tier}</p>
            <p className="text-xs text-muted-foreground">
              {profile.tier_source ? `via ${profile.tier_source}` : "Default"}
            </p>
          </div>
          <div className="flex flex-col gap-2 text-right">
            {upgradeReady && (
              <Link
                href="/pricing"
                className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
              >
                Upgrade
              </Link>
            )}
            {manageUrl && tier !== "free" && (
              <a
                href={manageUrl}
                target="_blank"
                rel="noreferrer"
                className="text-sm underline"
              >
                Manage billing →
              </a>
            )}
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="Tier limits">
        <ul className="grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
          <Stat label="Messages per day" value={limits.messages_per_day.toLocaleString()} />
          <Stat
            label="Council runs"
            value={`${limits.council_runs.limit}/${limits.council_runs.period}`}
          />
          <Stat
            label="Active personas"
            value={limits.active_personas === null ? "Unlimited" : `${limits.active_personas}`}
          />
          <Stat
            label="Couple links"
            value={limits.couple_links_active === 0 ? "—" : `${limits.couple_links_active}`}
          />
          <Stat
            label="Group seats / room"
            value={limits.group_seats_per_room === 0 ? "—" : `${limits.group_seats_per_room}`}
          />
          <Stat
            label="Active wagers"
            value={limits.wager_active_stakes === 0 ? "—" : `${limits.wager_active_stakes}`}
          />
          <Stat
            label="Roast Feed posts / week"
            value={limits.roast_feed_posts_per_week === 0 ? "Read only" : `${limits.roast_feed_posts_per_week}`}
          />
          <Stat
            label="Contradiction depth"
            value={
              limits.contradiction_wall_depth_days === null
                ? "Forever"
                : `${limits.contradiction_wall_depth_days} days`
            }
          />
        </ul>
      </SettingsSection>

      <SettingsSection
        title="Active subscription"
        description="Polar holds the source of truth for renewal and invoices."
      >
        {!active ? (
          <p className="text-sm text-muted-foreground">No active paid subscription.</p>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            <li className="flex justify-between">
              <span className="text-muted-foreground">Status</span>
              <span className="font-medium uppercase">{active.status}</span>
            </li>
            <li className="flex justify-between">
              <span className="text-muted-foreground">Source</span>
              <span className="font-medium">{active.source}</span>
            </li>
            <li className="flex justify-between">
              <span className="text-muted-foreground">Current period</span>
              <span>
                {fmtDate(active.current_period_start)} → {fmtDate(active.current_period_end)}
              </span>
            </li>
            <li className="flex justify-between">
              <span className="text-muted-foreground">Renews</span>
              <span>{active.cancel_at_period_end ? "No — cancels at period end" : "Yes"}</span>
            </li>
          </ul>
        )}
      </SettingsSection>

      {!polarEnabled() && (
        <p className="text-xs text-muted-foreground">
          Payments are gated behind <code>ENABLE_POLAR</code>. While that&apos;s off,
          tiers are manually assigned and no real charges occur.
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex justify-between rounded-md border border-input px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </li>
  );
}
