import { BreakupAnalyzerForm } from "./BreakupAnalyzerForm";

export default function BreakupAnalyzerPage() {
  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Breakup Analyzer</h1>
        <p className="text-sm text-muted-foreground">
          Paste the last 24-48 hours of texts. The AI reads the attachment
          dynamics, judges how likely reconciliation actually is (not how much
          you want it), names what you&apos;re missing, and drafts the message
          you could send next — repair-direction or end-direction.
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Costs 3 messages from your daily quota.
        </p>
      </header>
      <div className="mt-6">
        <BreakupAnalyzerForm />
      </div>
    </main>
  );
}
