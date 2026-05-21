// EU AI Act Article 50 disclosure helpers (CLAUDE.md §11 step 9, §27 step 55).
//
// The onboarding flow captures the *acknowledgement* via the legal-step
// checkbox (profiles.onboarding_completed_at carries the audit signal). This
// helper layer drives the *runtime* disclosure — a one-time modal shown the
// first time the visitor enters the authenticated app on a given device.
//
// We deliberately use a cookie rather than a profiles column:
//   - it survives sign-out and is easy to reset for testing,
//   - it covers anonymous visitors who land on /chat via a deep link before
//     authentication completes,
//   - we are not the audit-of-record for legal acknowledgement (the
//     onboarding step is); the cookie is a UX hint.
//
// The write side (setting the cookie) lives in a server action — see
// app/(app)/_actions/eu-ai-act.ts — because cookie *mutation* is only
// allowed from Server Actions and Route Handlers in Next 15.

import { cookies } from "next/headers";

export const EU_AI_ACT_COOKIE = "quarrel_eu_ai_ack";
export const EU_AI_ACT_COOKIE_TTL_SECONDS = 60 * 60 * 24 * 365;

export async function hasAcknowledgedAiDisclosure(): Promise<boolean> {
  const store = await cookies();
  const value = store.get(EU_AI_ACT_COOKIE)?.value;
  return Boolean(value && value.length > 0);
}
