// Wagers helpers (§9.5.5, §8.1).
//
// Stake bounds and active-wagers caps come from packages/shared
// TIER_LIMITS so the per-tier numbers stay in one place. Currency
// formatting is centralised here too — wagers display USD throughout
// (§9.5.5 doesn't specify other currencies yet; §9.6 anti-charities
// are US-flagged).

import {
  TIER_LIMITS,
  WAGER_MAX_STAKE_CENTS_ABSOLUTE,
  WAGER_MIN_STAKE_CENTS,
  type Tier,
} from "@quarrel/shared/constants";

export function maxActiveWagersForTier(tier: Tier): number {
  return TIER_LIMITS[tier].wager_active_stakes;
}

export function maxStakeCentsForTier(tier: Tier): number {
  return Math.min(
    TIER_LIMITS[tier].wager_max_stake_cents,
    WAGER_MAX_STAKE_CENTS_ABSOLUTE,
  );
}

export function minStakeCents(): number {
  return WAGER_MIN_STAKE_CENTS;
}

export function formatCents(cents: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

/**
 * Polar integration is gated on this server-side env. When false (default
 * during pre-launch) we mock the auth-and-capture flow — wagers go straight
 * to `active`. When true (post-§27 step 47-48), creation initiates a real
 * Polar checkout and the webhook handler moves rows pending → active.
 */
export function polarEnabled(): boolean {
  return process.env.ENABLE_POLAR === "true";
}

/** Days from start to end, rounded up to whole days. */
export function wagerDurationDays(startAt: string, endAt: string): number {
  const start = new Date(startAt).getTime();
  const end = new Date(endAt).getTime();
  return Math.max(1, Math.ceil((end - start) / 86_400_000));
}
