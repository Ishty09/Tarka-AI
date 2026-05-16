import { OnboardingShell } from "../_components/Shell";
import { IntentForm } from "./IntentForm";

export default function IntentPage() {
  return (
    <OnboardingShell
      step="intent"
      title="What brings you here?"
      subline="Pick up to three. We use them to suggest a starting persona."
    >
      <IntentForm />
    </OnboardingShell>
  );
}
