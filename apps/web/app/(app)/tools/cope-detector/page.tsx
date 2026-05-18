import { CopeDetectorForm } from "./CopeDetectorForm";

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
        <CopeDetectorForm />
      </div>
    </main>
  );
}
