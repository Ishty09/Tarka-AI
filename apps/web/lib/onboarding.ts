// Onboarding state machine. Source of truth for "what step does the user
// resume at?". Used by /onboarding (root) to redirect.
//
// Schema gap (see commit body): we don't have an onboarding_state table, and
// several §11 steps (intent, persona pick, emergency contact) either don't
// persist anything or write optional columns we can't distinguish from "not
// visited". So the resume logic only checks columns that MUST be set by a
// real human (username + age_range), plus the terminal flag. Forward
// navigation through the middle pages is linear via "Continue" buttons.

import type { ProfilesRow } from "@quarrel/shared/schemas";

export const ONBOARDING_STEPS = [
  "welcome",
  "profile",
  "locale",
  "age",
  "intent",
  "persona",
  "daily-roast",
  "emergency",
  "legal",
] as const;

export type OnboardingStep = (typeof ONBOARDING_STEPS)[number];

export const ONBOARDING_PATH: Record<OnboardingStep, string> = {
  welcome: "/onboarding/welcome",
  profile: "/onboarding/profile",
  locale: "/onboarding/locale",
  age: "/onboarding/age",
  intent: "/onboarding/intent",
  persona: "/onboarding/persona",
  "daily-roast": "/onboarding/daily-roast",
  emergency: "/onboarding/emergency",
  legal: "/onboarding/legal",
};

export function nextOnboardingStep(profile: ProfilesRow | null): OnboardingStep | "done" {
  if (profile?.onboarding_completed_at) return "done";
  if (!profile) return "welcome";
  if (!profile.age_range) return "age";
  // age_range was set but legal wasn't — resume at legal. The user may have
  // skipped through intent / persona / daily-roast / emergency without
  // writing anything we can detect, but legal is the only required final.
  return "legal";
}

export function nextStepPath(step: OnboardingStep): string {
  const idx = ONBOARDING_STEPS.indexOf(step);
  const next = ONBOARDING_STEPS[idx + 1];
  return next ? ONBOARDING_PATH[next] : "/chat";
}

/** Used by progress UI — 1-indexed for human display. */
export function stepNumber(step: OnboardingStep): number {
  return ONBOARDING_STEPS.indexOf(step) + 1;
}

export const TOTAL_STEPS = ONBOARDING_STEPS.length;
