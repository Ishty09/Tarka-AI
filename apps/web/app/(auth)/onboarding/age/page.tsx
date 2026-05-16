import { OnboardingShell } from "../_components/Shell";
import { AgeForm } from "./AgeForm";

export default function AgePage() {
  return (
    <OnboardingShell
      step="age"
      title="How old are you?"
      subline="Couples, wagers, marketplace, and the feed are 16+. Under 16 keeps core chat only."
    >
      <AgeForm />
    </OnboardingShell>
  );
}
