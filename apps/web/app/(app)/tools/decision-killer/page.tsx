import { DecisionKillerForm } from "./DecisionKillerForm";

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
        <DecisionKillerForm />
      </div>
    </main>
  );
}
