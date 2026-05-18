import { CouncilForm } from "./CouncilForm";

// Council tool entry point (§9.1.2). The page is mostly chrome — all the
// state lives in the client component that posts to /api/tools/council.

export default function CouncilPage() {
  return (
    <main className="mx-auto w-full max-w-5xl p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Council</h1>
        <p className="text-sm text-muted-foreground">
          Five councilors, five lenses, one judge. Submit a dilemma — you&apos;ll get
          honest takes from the Stoic, Economist, Therapist, Skeptic, and Insider,
          plus a synthesised verdict.
        </p>
      </header>
      <div className="mt-6">
        <CouncilForm />
      </div>
    </main>
  );
}
