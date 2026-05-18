import { redirect } from "next/navigation";
import Link from "next/link";
import { createServerSupabase } from "@/lib/supabase/server";
import { CritiqueLauncher } from "./CritiqueLauncher";

interface PageProps {
  params: Promise<{ id: string }>;
}

type SessionRow = {
  id: string;
  title: string | null;
  metadata: Record<string, unknown> | null;
};

export default async function NegotiationCritiquePage({ params }: PageProps) {
  const { id } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: sessionData } = await supabase
    .from("conversations")
    .select("id, title, metadata")
    .eq("id", id)
    .eq("user_id", user.id)
    .eq("mode", "negotiate")
    .maybeSingle();
  const session = sessionData as SessionRow | null;
  if (!session) {
    return (
      <main className="mx-auto w-full max-w-3xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          We couldn&apos;t find that negotiation session. It may have been archived
          or it was never yours.
        </p>
        <Link href="/tools/negotiation-sparring" className="mt-4 inline-block text-sm underline">
          Back to scenarios
        </Link>
      </main>
    );
  }

  // If a critique already lives in this conversation, render it directly so a
  // repeat visit doesn't burn another quarrel-argue call.
  const { data: existing } = await supabase
    .from("messages")
    .select("id, content, metadata, created_at")
    .eq("conversation_id", id)
    .order("created_at", { ascending: false })
    .limit(10);

  const cached = (existing ?? []).find((m: { metadata: Record<string, unknown> | null }) => {
    const meta = m.metadata ?? {};
    return typeof meta === "object" && (meta as Record<string, unknown>).kind === "negotiation_critique";
  }) as
    | {
        id: number;
        content: string;
        metadata: { strengths?: string[]; weaknesses?: string[]; alternative?: string };
      }
    | undefined;

  const meta = session.metadata ?? {};
  const scenarioTitle = typeof meta.scenario_title === "string"
    ? meta.scenario_title
    : (session.title ?? "Session");
  const counterparty = typeof meta.counterparty === "string" ? meta.counterparty : null;

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <Link href="/tools/negotiation-sparring" className="text-sm text-muted-foreground hover:underline">
        ← All sessions
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Critique</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        {scenarioTitle}{counterparty ? ` · vs ${counterparty}` : ""}
      </p>

      {cached ? (
        <CachedCritique critique={cached} />
      ) : (
        <CritiqueLauncher conversationId={session.id} />
      )}

      <div className="mt-6 text-xs text-muted-foreground">
        <Link href={`/chat/${session.id}`} className="underline">
          Open the full conversation
        </Link>
      </div>
    </main>
  );
}

function CachedCritique({
  critique,
}: {
  critique: {
    content: string;
    metadata: { strengths?: string[]; weaknesses?: string[]; alternative?: string };
  };
}) {
  const meta = critique.metadata;
  return (
    <div className="mt-6 flex flex-col gap-4">
      <Panel title="Strengths" items={meta.strengths ?? []} tone="positive" />
      <Panel title="Weaknesses" items={meta.weaknesses ?? []} tone="negative" />
      <section className="rounded-md border border-primary/40 bg-primary/5 p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary/90">
          What to try next time
        </h2>
        <p className="mt-2 text-sm leading-relaxed">
          {meta.alternative ?? "—"}
        </p>
      </section>
    </div>
  );
}

function Panel({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "positive" | "negative";
}) {
  const border = tone === "positive" ? "border-emerald-500/30 bg-emerald-500/5" : "border-red-500/30 bg-red-500/5";
  const heading = tone === "positive" ? "text-emerald-700/90" : "text-red-700/90";
  return (
    <section className={`rounded-md border ${border} p-4 shadow-sm`}>
      <h2 className={`text-sm font-semibold uppercase tracking-wide ${heading}`}>{title}</h2>
      <ol className="mt-2 flex flex-col gap-2 text-sm">
        {items.map((item, i) => (
          <li key={i}>
            <span className="font-medium">{i + 1}.</span> {item}
          </li>
        ))}
      </ol>
    </section>
  );
}
