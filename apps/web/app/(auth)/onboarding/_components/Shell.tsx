import { TOTAL_STEPS, type OnboardingStep, stepNumber } from "@/lib/onboarding";

// Shared chrome for every onboarding page. Renders the progress indicator
// and a centered card. Each page passes the step name + its content.

export function OnboardingShell({
  step,
  title,
  subline,
  children,
}: {
  step: OnboardingStep;
  title: string;
  subline?: string;
  children: React.ReactNode;
}) {
  const current = stepNumber(step);
  const pct = Math.round((current / TOTAL_STEPS) * 100);

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="w-full max-w-md flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Step {current} of {TOTAL_STEPS}</span>
            <span>{pct}%</span>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>

        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {subline && <p className="text-sm text-muted-foreground">{subline}</p>}
        </header>

        {children}
      </div>
    </main>
  );
}
