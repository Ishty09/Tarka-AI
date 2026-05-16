import { OnboardingShell } from "../_components/Shell";

// §11 step 1 — two buttons. "I want a yes-man" sends them to ChatGPT (the
// spec explicitly says "yes, actually"). No DB write.

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
        <a
          href="https://chat.openai.com"
          rel="noreferrer"
          className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-2 text-sm font-medium shadow-sm hover:bg-accent"
        >
          I want a yes-man
        </a>
        <p className="text-xs text-muted-foreground">
          Picking option two opens ChatGPT. That&apos;s the right tool if you want validation.
        </p>
      </div>
    </OnboardingShell>
  );
}
