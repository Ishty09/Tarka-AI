import { DecisionKillerForm } from "./DecisionKillerForm";
import { RecentRuns } from "../_components/RecentRuns";

const EXAMPLES: string[] = [
  "I'm thinking about quitting my engineering job to do my side project full time. I've been saving for a year and have 14 months runway. The side project has ~200 paying users and $2k MRR.",
  "I want to text my ex after 6 months of no contact. We didn't end on bad terms. I miss them but I'm also dating someone new who's been good to me.",
  "I'm about to accept a job offer that's 30% more money but at a company whose mission I don't really care about. My current role is mission-aligned but stagnating.",
];

export default function DecisionKillerPage() {
  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Decision Killer</h1>
        <p className="text-sm text-muted-foreground">
          Paste a decision you&apos;re about to make. You&apos;ll get the three
          strongest reasons it&apos;s wrong, the strongest reason it might be right,
          and one sentence naming what you&apos;re actually avoiding.
        </p>
      </header>
      <div className="mt-6">
        <DecisionKillerForm examples={EXAMPLES} />
      </div>
      <RecentRuns mode="decision_killer" />
    </main>
  );
}
