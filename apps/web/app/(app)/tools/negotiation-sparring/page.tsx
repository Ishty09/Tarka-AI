import { redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { ScenarioPicker } from "./ScenarioPicker";

// Negotiation Sparring landing (§9.5.3). Shows the scenario picker on top
// and any past negotiation sessions below, each with a "Get critique" link.

type ConversationRow = {
  id: string;
  title: string | null;
  updated_at: string;
  metadata: Record<string, unknown> | null;
};

export default async function NegotiationSparringPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: sessions } = await supabase
    .from("conversations")
    .select("id, title, updated_at, metadata")
    .eq("user_id", user.id)
    .eq("mode", "negotiate")
    .eq("archived", false)
    .order("updated_at", { ascending: false })
    .limit(20);

  const rows = (sessions ?? []) as unknown as ConversationRow[];

  return (
    <main className="mx-auto w-full max-w-4xl p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Negotiation Sparring</h1>
        <p className="text-sm text-muted-foreground">
          Pick a scenario. The AI plays the hostile counterparty for as many
          turns as you can hold. When you&apos;re done, ask for a critique — three
          strengths, three weaknesses, one alternative to try next time.
        </p>
      </header>

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Start a session
        </h2>
        <div className="mt-3">
          <ScenarioPicker />
        </div>
      </section>

      {rows.length > 0 && (
        <section className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Your past sessions
          </h2>
          <ul className="mt-3 flex flex-col gap-2">
            {rows.map((row) => {
              const meta = row.metadata ?? {};
              const counterparty = typeof meta.counterparty === "string"
                ? meta.counterparty
                : null;
              return (
                <li
                  key={row.id}
                  className="flex items-center justify-between gap-3 rounded-md border border-input bg-background px-4 py-3 text-sm shadow-sm"
                >
                  <div className="flex flex-col">
                    <span className="font-medium">{row.title ?? "Untitled session"}</span>
                    <span className="text-xs text-muted-foreground">
                      vs {counterparty ?? "—"} · {new Date(row.updated_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/chat/${row.id}`}
                      className="rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent"
                    >
                      Resume
                    </Link>
                    <Link
                      href={`/tools/negotiation-sparring/${row.id}/critique`}
                      className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:opacity-90"
                    >
                      Get critique
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </main>
  );
}
