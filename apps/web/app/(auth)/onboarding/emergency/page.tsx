import { OnboardingShell } from "../_components/Shell";
import { EmergencyForm } from "./EmergencyForm";

interface PageProps {
  searchParams: Promise<{ persona?: string }>;
}

export default async function EmergencyPage({ searchParams }: PageProps) {
  const { persona } = await searchParams;
  return (
    <OnboardingShell
      step="emergency"
      title="Emergency contact (optional)"
      subline="Only used if you express clear crisis signals more than once in 24 hours."
    >
      <EmergencyForm personaCarry={persona ?? ""} />
    </OnboardingShell>
  );
}
