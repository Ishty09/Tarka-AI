import { FutureSelfForm } from "./FutureSelfForm";

export default function FutureSelfPage() {
  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Future Self</h1>
        <p className="text-sm text-muted-foreground">
          Describe the decision you&apos;re weighing. The AI plays you at 80,
          looking back — wise, regretful, urgent. The version of you who
          already knows what this costs.
        </p>
      </header>
      <div className="mt-6">
        <FutureSelfForm />
      </div>
    </main>
  );
}
