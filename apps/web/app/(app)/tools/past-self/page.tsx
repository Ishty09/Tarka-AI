import { PastSelfForm } from "./PastSelfForm";

export default function PastSelfPage() {
  return (
    <main className="mx-auto w-full max-w-5xl p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Past Self</h1>
        <p className="text-sm text-muted-foreground">
          Paste a journal entry, an old tweet, a message you sent years ago. The
          AI takes the strongest position opposite your past self. You judge
          which version was right.
        </p>
      </header>
      <div className="mt-6">
        <PastSelfForm />
      </div>
    </main>
  );
}
