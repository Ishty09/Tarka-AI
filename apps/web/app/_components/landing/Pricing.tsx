import Link from "next/link";
import { TIER_LIMITS } from "@quarrel/shared/constants";

// Pricing summary on the landing page (CLAUDE.md §17, §18). Three cards,
// linked to the dedicated /pricing page for the full comparison.

const TIERS = [
  {
    tier: "free" as const,
    name: "Free",
    price: "$0",
    cadence: "forever",
    cta: { href: "/signup", label: "Start free" },
    highlight: false,
    pitch: "Enough to feel the pushback. Not enough to drown in it.",
  },
  {
    tier: "pro" as const,
    name: "Pro",
    price: "$9.99",
    cadence: "per month",
    cta: { href: "/signup?next=/settings/billing", label: "Go Pro" },
    highlight: true,
    pitch: "When 15 messages a day isn't enough — and you want partner mode.",
  },
  {
    tier: "max" as const,
    name: "Max",
    price: "$24.99",
    cadence: "per month",
    cta: { href: "/signup?next=/settings/billing", label: "Go Max" },
    highlight: false,
    pitch: "Founders, writers, and anyone doing real work with the model.",
  },
];

function fmt(n: number): string {
  if (n >= 1000) {
    return `${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}K`;
  }
  return String(n);
}

export function Pricing() {
  return (
    <section className="border-b">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            Every feature on every tier. Only the limits differ.
          </h2>
          <p className="mt-4 text-sm text-muted-foreground md:text-base">
            14-day money-back guarantee on first payment.
          </p>
        </div>

        <ul className="mt-12 grid gap-6 md:grid-cols-3">
          {TIERS.map((t) => {
            const limits = TIER_LIMITS[t.tier];
            return (
              <li
                key={t.tier}
                className={`flex flex-col gap-5 rounded-xl border p-6 shadow-sm ${
                  t.highlight
                    ? "border-foreground/40 bg-card ring-1 ring-foreground/10"
                    : "bg-card"
                }`}
              >
                <div>
                  <h3 className="text-lg font-semibold">{t.name}</h3>
                  <p className="mt-2 flex items-baseline gap-1">
                    <span className="text-3xl font-semibold tracking-tight">
                      {t.price}
                    </span>
                    <span className="text-sm text-muted-foreground">/{t.cadence}</span>
                  </p>
                  <p className="mt-3 text-sm text-muted-foreground">{t.pitch}</p>
                </div>

                <ul className="flex flex-col gap-1.5 text-sm">
                  <li>{fmt(limits.messages_per_day)} messages / day</li>
                  <li>
                    {limits.council_runs.limit} Council run
                    {limits.council_runs.limit > 1 ? "s" : ""} /{" "}
                    {limits.council_runs.period}
                  </li>
                  <li>
                    {limits.couple_links_active === 0
                      ? "Couples mode locked"
                      : `${limits.couple_links_active} couple link${limits.couple_links_active > 1 ? "s" : ""}`}
                  </li>
                  <li>
                    Memory depth:{" "}
                    {t.tier === "free"
                      ? "30 days"
                      : t.tier === "pro"
                      ? "1 year"
                      : "Forever"}
                  </li>
                  <li>Context: {fmt(limits.context_window_tokens)} tokens</li>
                </ul>

                <Link
                  href={t.cta.href}
                  className={`mt-auto inline-flex items-center justify-center rounded-md px-4 py-2.5 text-sm font-medium ${
                    t.highlight
                      ? "bg-primary text-primary-foreground hover:opacity-90"
                      : "border border-input hover:bg-accent hover:text-accent-foreground"
                  }`}
                >
                  {t.cta.label}
                </Link>
              </li>
            );
          })}
        </ul>

        <p className="mt-8 text-center text-sm text-muted-foreground">
          Need the full comparison?{" "}
          <Link href="/pricing" className="underline underline-offset-2">
            See pricing →
          </Link>
        </p>
      </div>
    </section>
  );
}
