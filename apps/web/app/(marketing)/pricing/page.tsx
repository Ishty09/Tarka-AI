import Link from "next/link";
import { TIER_LIMITS } from "@quarrel/shared/constants";
import { polarEnabled } from "@/lib/wagers";
import { CheckoutForm } from "./CheckoutForm";
import { ComparisonTable } from "./ComparisonTable";
import { PricingFAQ } from "./PricingFAQ";

// Pricing page — three tiers, billing-interval toggle. All features at
// every tier (§8); the columns spell out the per-tier limits. CTAs
// kick off Polar checkouts via a server action; if the visitor isn't
// signed in the action redirects them to /login first.

export const metadata = {
  title: "Pricing | Quarrel",
  description: "Three tiers, every feature on each. Free trial, Pro $9.99/mo, Max $24.99/mo.",
};

interface PageProps {
  searchParams?: Promise<{ interval?: string }>;
}

export default async function PricingPage({ searchParams }: PageProps) {
  const params = (await searchParams) ?? {};
  const interval: "monthly" | "annual" = params.interval === "annual" ? "annual" : "monthly";
  const enabled = polarEnabled();

  const proPrice = interval === "monthly" ? "$9.99" : "$79";
  const maxPrice = interval === "monthly" ? "$24.99" : "$199";
  const proSuffix = interval === "monthly" ? "/mo" : "/yr · $6.58/mo";
  const maxSuffix = interval === "monthly" ? "/mo" : "/yr · $16.58/mo";

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-10 p-8">
      <header className="flex flex-col items-center gap-3 text-center">
        <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
          Three tiers. Every feature on each.
        </h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Only the limits differ. The AI doesn&apos;t get nicer at higher tiers.
        </p>
        <div className="mt-2 inline-flex items-center rounded-full border border-input bg-card p-1 text-xs">
          <Link
            href="/pricing?interval=monthly"
            className={`rounded-full px-3 py-1 ${
              interval === "monthly" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
            }`}
          >
            Monthly
          </Link>
          <Link
            href="/pricing?interval=annual"
            className={`rounded-full px-3 py-1 ${
              interval === "annual" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
            }`}
          >
            Annual · save ~30%
          </Link>
        </div>
        {!enabled && (
          <p className="text-[11px] text-amber-600">
            Payments aren&apos;t switched on yet; buttons will say so when you click them.
          </p>
        )}
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <TierCard
          tier="free"
          name="Free"
          price="$0"
          suffix=""
          highlights={[
            `${TIER_LIMITS.free.messages_per_day} messages/day`,
            `${TIER_LIMITS.free.council_runs.limit}/${TIER_LIMITS.free.council_runs.period} Council runs`,
            `${TIER_LIMITS.free.active_personas} personas`,
            "Contradictions 30 days",
          ]}
          cta={<Link href="/signup" className="text-center underline">Start free →</Link>}
        />
        <TierCard
          tier="pro"
          name="Pro"
          price={proPrice}
          suffix={proSuffix}
          highlights={[
            `${TIER_LIMITS.pro.messages_per_day} messages/day`,
            `${TIER_LIMITS.pro.council_runs.limit}/${TIER_LIMITS.pro.council_runs.period} Council runs`,
            `${TIER_LIMITS.pro.active_personas} personas`,
            `${TIER_LIMITS.pro.couple_links_active} couple link`,
            "Contradictions 1 year",
            "Mirror Mode weekly",
          ]}
          accent
          cta={<CheckoutForm tier="pro" interval={interval} />}
        />
        <TierCard
          tier="max"
          name="Max"
          price={maxPrice}
          suffix={maxSuffix}
          highlights={[
            `${TIER_LIMITS.max.messages_per_day} messages/day`,
            `${TIER_LIMITS.max.council_runs.limit}/${TIER_LIMITS.max.council_runs.period} Council runs`,
            "Unlimited personas",
            `${TIER_LIMITS.max.couple_links_active} couple links`,
            "Contradictions forever",
            "Mirror Mode weekly + on-demand",
            "Eulogy quarterly + on-demand",
          ]}
          cta={<CheckoutForm tier="max" interval={interval} />}
        />
      </div>

      <p className="text-center text-xs text-muted-foreground">
        14-day money-back guarantee. Cancel any time in{" "}
        <Link href="/settings/billing" className="underline">
          Settings → Billing
        </Link>
        .
      </p>

      <section className="mt-6 flex flex-col gap-3">
        <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">
          Side-by-side.
        </h2>
        <p className="text-sm text-muted-foreground">
          Every feature is available at every tier. These are the limits the
          system actually enforces.
        </p>
        <ComparisonTable />
      </section>

      <PricingFAQ />
    </main>
  );
}

function TierCard({
  name,
  price,
  suffix,
  highlights,
  cta,
  accent = false,
}: {
  tier: string;
  name: string;
  price: string;
  suffix: string;
  highlights: string[];
  cta: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <article
      className={`flex flex-col gap-3 rounded-xl border bg-card p-6 shadow-sm ${
        accent ? "border-primary/40 ring-1 ring-primary/20" : "border-input"
      }`}
    >
      <h2 className="text-lg font-semibold tracking-tight">{name}</h2>
      <div className="flex items-baseline gap-1">
        <span className="text-3xl font-semibold">{price}</span>
        <span className="text-xs text-muted-foreground">{suffix}</span>
      </div>
      <ul className="flex flex-col gap-1.5 text-sm text-muted-foreground">
        {highlights.map((h) => (
          <li key={h}>• {h}</li>
        ))}
      </ul>
      <div className="mt-2">{cta}</div>
    </article>
  );
}
