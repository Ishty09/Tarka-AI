import { OnboardingShell } from "../_components/Shell";

// §11 step 1 — single confirmation button. The original spec had a
// second "I want a yes-man → ChatGPT" link as a punchline, but
// shipping a competitor link inside our signup funnel cost real
// activation, so it's been retired (decision log 2026-05-28).

export default function WelcomePage() {
  return (
    <OnboardingShell
      step="welcome"
      title="Quarrel won't lie to you."
      subline="Confirm you want that."
    >
      <div className="flex flex-col gap-3">
        <a
          href="/onboarding/profile"
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          I want that
        </a>
        <p className="text-xs text-muted-foreground">
          One click in and you&apos;ve agreed to be argued with.
        </p>
      </div>
    </OnboardingShell>
  );
}
