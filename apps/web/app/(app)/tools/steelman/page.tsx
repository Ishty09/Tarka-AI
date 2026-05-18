import { SteelmanForm } from "./SteelmanForm";

export default function SteelmanPage() {
  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Steelman</h1>
        <p className="text-sm text-muted-foreground">
          Paste a position you hold weakly. The AI will rebuild it as a careful
          proponent would, then surface the three strongest counters and how the
          steelmanned position handles them.
        </p>
      </header>
      <div className="mt-6">
        <SteelmanForm />
      </div>
    </main>
  );
}
