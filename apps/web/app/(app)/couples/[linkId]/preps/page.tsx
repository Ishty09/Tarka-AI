import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { NewPrepForm } from "./NewPrepForm";

interface PageProps {
  params: Promise<{ linkId: string }>;
}

interface PrepRow {
  id: string;
  topic: string;
  status: string;
  created_at: string;
  generated_at: string | null;
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  pending: { label: "Pending", cls: "bg-amber-500/20 text-amber-900 dark:text-amber-200" },
  generating: { label: "Generating…", cls: "bg-blue-500/20 text-blue-900 dark:text-blue-200" },
  ready: { label: "Ready", cls: "bg-emerald-500/20 text-emerald-900 dark:text-emerald-200" },
  failed: { label: "Failed", cls: "bg-destructive/20 text-destructive" },
};

export default async function CouplePrepsPage({ params }: PageProps) {
  const { linkId } = await params;
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: link } = await supabase
    .from("couple_links")
    .select("user_a, user_b, status")
    .eq("id", linkId)
    .maybeSingle();
  if (!link || link.status !== "active") redirect("/couples");
  if (user.id !== link.user_a && user.id !== link.user_b) redirect("/couples");

  // RLS already scopes to user_id = auth.uid() — these are MY preps only.
  const { data: rawPreps } = await supabase
    .from("couple_conversation_preps")
    .select("id, topic, status, created_at, generated_at")
    .eq("couple_link_id", linkId)
    .order("created_at", { ascending: false })
    .limit(30);
  const preps: PrepRow[] = (rawPreps ?? []) as unknown as PrepRow[];

  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <Link
        href={`/couples/${linkId}`}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ← Back to couple
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        Pre-conversation prep
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Private to you. Before a hard talk, get talking points + what your
        partner might say + de-escalation paths. They never see this.
      </p>

      <section className="mt-6 rounded-lg border border-input bg-card p-4">
        <h2 className="text-sm font-semibold">New prep</h2>
        <NewPrepForm linkId={linkId} />
      </section>

      {preps.length === 0 ? (
        <p className="mt-8 text-center text-xs text-muted-foreground">
          No preps yet. Start one above before your next hard talk.
        </p>
      ) : (
        <section className="mt-8">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Your preps
          </h2>
          <ul className="flex flex-col gap-2">
            {preps.map((p) => {
              const meta = STATUS_META[p.status] ?? STATUS_META.pending;
              return (
                <li key={p.id}>
                  <Link
                    href={`/couples/${linkId}/preps/${p.id}`}
                    className="flex items-center justify-between gap-3 rounded-lg border border-input bg-card px-4 py-3 text-sm shadow-sm transition hover:border-primary/40 hover:bg-accent"
                  >
                    <div className="flex flex-col gap-0.5">
                      <span className="font-medium">{p.topic}</span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(p.created_at).toLocaleString()}
                      </span>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${meta.cls}`}
                    >
                      {meta.label}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </main>
  );
}
