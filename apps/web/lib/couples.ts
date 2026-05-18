// Couples link helpers (§9.3.1).
//
// Centralises the invite-code generation, expiry window, and the
// tier→active-link cap so the §8.1 limits don't drift across files.

import { TIER_LIMITS, type Tier } from "@quarrel/shared/constants";

export const INVITE_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

/**
 * URL-safe random invite code. Crockford-base32 alphabet without I, L, O, U
 * so a human reading it out loud doesn't trip over confusable chars.
 */
export function generateInviteCode(length = 16): string {
  const alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  let out = "";
  for (let i = 0; i < length; i++) {
    out += alphabet[bytes[i] & 31];
  }
  return out;
}

export function inviteExpiry(now = Date.now()): string {
  return new Date(now + INVITE_TTL_MS).toISOString();
}

export function activeCoupleLimitFor(tier: Tier): number {
  return TIER_LIMITS[tier].couple_links_active;
}
