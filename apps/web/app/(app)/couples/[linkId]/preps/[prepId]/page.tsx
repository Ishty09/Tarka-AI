import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

interface PageProps {
  params: Promise<{ linkId: string; prepId: string }>;
}

interface Prep {
  id: string;
  topic: string;
  desired_outcome: string | null;
  status: string;
  prep: {
    talking_points?: string[];
    partner_might_say?: { statement: string; actually_means: string }[];
    deescalation_paths?: string[];
    opening_line?: string;
    watch_out_for?: string;
  } | null;
  created_at: string;
  generated_at: string | null;
}

export default async function PrepDetailPage({ params }: PageProps) {
  const { linkId, prepId } = await params;
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

  // RLS gates: user_id = auth.uid() ensures only the owner sees their prep.
  const { data: rawPrep } = await supabase
    .from("couple_conversation_preps")
    .select("id, topic, desired_outcome, status, prep, created_at, generated_at")
    .eq("id", prepId)
    .maybeSingle();
  const p = rawPrep as unknown as Prep | null;
  if (!p) redirect(`/couples/${linkId}/preps`);

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <Link
        href={`/couples/${linkId}/preps`}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ← Back to preps
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{p.topic}</h1>
      {p.desired_outcome && (
        <p className="mt-1 text-sm text-muted-foreground">
          Desired outcome: {p.desired_outcome}
        </p>
      )}
      <p className="mt-1 text-xs text-muted-foreground">
        🔒 Private to you — your partner does not see this.
      </p>

      {p.status === "generating" && (
        <div className="mt-6 rounded-lg border border-blue-500/40 bg-blue-500/10 p-4 text-sm">
          Generating prep… refresh in ~10s.
        </div>
      )}

      {p.status === "failed" && (
        <div className="mt-6 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm">
          Generation failed. Refresh to retry, or create a new prep.
        </div>
      )}

      {p.status === "ready" && p.prep && (
        <div className="mt-6 space-y-4">
          {p.prep.opening_line && (
            <section className="rounded-lg border border-primary/40 bg-primary/5 p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Opening line — say this first
              </h2>
              <p className="mt-2 text-base font-medium leading-relaxed">
                &ldquo;{p.prep.opening_line}&rdquo;
              </p>
            </section>
          )}

          {p.prep.talking_points && p.prep.talking_points.length > 0 && (
            <section className="rounded-lg border border-input bg-card p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Your talking points
              </h2>
              <ul className="mt-2 list-decimal space-y-1.5 pl-5 text-sm leading-relaxed">
                {p.prep.talking_points.map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            </section>
          )}

          {p.prep.partner_might_say && p.prep.partner_might_say.length > 0 && (
            <section className="rounded-lg border border-input bg-card p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                What your partner might say (and what it actually means)
              </h2>
              <ul className="mt-2 space-y-3 text-sm">
                {p.prep.partner_might_say.map((s, i) => (
                  <li key={i} className="border-l-2 border-violet-500/40 pl-3">
                    <p className="italic">&ldquo;{s.statement}&rdquo;</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Actually means: {s.actually_means}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {p.prep.deescalation_paths && p.prep.deescalation_paths.length > 0 && (
            <section className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-emerald-800 dark:text-emerald-300">
                If it heats up
              </h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                {p.prep.deescalation_paths.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </section>
          )}

          {p.prep.watch_out_for && (
            <section className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
                Watch out for (about you)
              </h2>
              <p className="mt-2 text-sm leading-relaxed">{p.prep.watch_out_for}</p>
            </section>
          )}
        </div>
      )}
    </main>
  );
}
