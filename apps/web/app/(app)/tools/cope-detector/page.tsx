import { CopeDetectorForm } from "./CopeDetectorForm";
import { RecentRuns } from "../_components/RecentRuns";

const EXAMPLES: string[] = [
  "I'll start the new project after I finish the one I'm on — it's only fair to the team. They've been depending on me and switching now would be selfish.",
  "I'm not ready to date again yet. I need to work on myself first. Once I really know who I am and what I want, then I'll be ready to bring that to someone.",
  "I'll go to the gym when work calms down. Right now my schedule is just too unpredictable and any routine I start will get destroyed by the next deadline.",
];

export default function CopeDetectorPage() {
  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Cope Detector</h1>
        <p className="text-sm text-muted-foreground">
          Paste the story you&apos;re telling yourself. You&apos;ll get the same
          rationalization mirrored back, the underlying thing you&apos;re
          avoiding, and the single question you&apos;re refusing to ask.
        </p>
      </header>
      <div className="mt-6">
        <CopeDetectorForm examples={EXAMPLES} />
      </div>
      <RecentRuns mode="cope_detector" />
    </main>
  );
}
