// Group rooms helpers (§9.3.4).
//
// Seat cap is per-room, not per-user. There's no per-user-rooms cap in
// §8.1 — a Pro user can be in N rooms, each of which has at most 5 seats.

import { TIER_LIMITS, type Tier } from "@quarrel/shared/constants";

export function maxSeatsForTier(tier: Tier): number {
  return TIER_LIMITS[tier].group_seats_per_room;
}

/**
 * URL-safe random invite code shared by every member of a group room.
 * Wider entropy than couples (longer) because the code lives on a row
 * that doesn't expire — re-rolling on rotation is a future feature.
 */
export function generateGroupInviteCode(length = 20): string {
  const alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  let out = "";
  for (let i = 0; i < length; i++) {
    out += alphabet[bytes[i] & 31];
  }
  return out;
}
