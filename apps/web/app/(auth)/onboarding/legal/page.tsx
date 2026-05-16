import { OnboardingShell } from "../_components/Shell";
import { LegalForm } from "./LegalForm";

interface PageProps {
  searchParams: Promise<{ persona?: string }>;
}

export default async function LegalPage({ searchParams }: PageProps) {
  const { persona } = await searchParams;
  return (
    <OnboardingShell
      step="legal"
      title="One more thing"
      subline="You are interacting with an AI system. Outputs are generated, not human."
    >
      <LegalForm personaCarry={persona ?? ""} />
    </OnboardingShell>
  );
}
