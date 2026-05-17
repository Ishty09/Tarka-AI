import Link from "next/link";

// Marketplace stub. ENABLE_PERSONA_MARKETPLACE is `false` in §5 for MVP;
// the actual marketplace (Phase ?? — not in §27) brings creator payouts
// via Polar (§3 payments) and ratings/reviews. For now this page exists
// so the §4 route is reachable and we can flip the flag when ready.

const ENABLED = process.env.ENABLE_PERSONA_MARKETPLACE === "true";

export default function MarketplacePage() {
  if (ENABLED) {
    // Real marketplace UI lands here once the feature flips on.
    return (
      <main className="mx-auto w-full max-w-3xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Marketplace</h1>
        <p className="mt-2 text-sm text-muted-foreground">Coming soon.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-2xl p-6 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Marketplace — closed for now</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Paid personas, ratings, and creator payouts are on the post-launch list.
        Build private personas in the meantime.
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <Link
          href="/personas/create"
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          Create a persona
        </Link>
        <Link
          href="/personas"
          className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-2 text-sm font-medium shadow-sm hover:bg-accent"
        >
          Back to library
        </Link>
      </div>
    </main>
  );
}
