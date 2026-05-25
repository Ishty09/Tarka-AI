import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

interface PageProps {
  params: Promise<{ linkId: string }>;
}

interface ReportRow {
  id: string;
  period_start: string;
  period_end: string;
  content: {
    themes?: string[];
    wins?: string[];
    watch?: string[];
    experiment?: string;
    effort_summary_a?: string;
    effort_summary_b?: string;
  };
  generated_at: string;
  viewed_a_at: string | null;
  viewed_b_at: string | null;
}

export default async function CoupleReportsPage({ params }: PageProps) {
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

  const { data: rawReports } = await supabase
    .from("couple_reports")
    .select(
      "id, period_start, period_end, content, generated_at, viewed_a_at, viewed_b_at"
    )
    .eq("couple_link_id", linkId)
    .order("period_start", { ascending: false })
    .limit(20);
  const reports: ReportRow[] = (rawReports ?? []) as unknown as ReportRow[];

  // Mark the latest as viewed for this user (best-effort).
  if (reports[0]) {
    const isA = user.id === link.user_a;
    const col = isA ? "viewed_a_at" : "viewed_b_at";
    if ((isA && !reports[0].viewed_a_at) || (!isA && !reports[0].viewed_b_at)) {
      await supabase
        .from("couple_reports")
        .update({ [col]: new Date().toISOString() })
        .eq("id", reports[0].id);
    }
  }

  const latest = reports[0];

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <Link
        href={`/couples/${linkId}`}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ← Back to couple
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        Weekly reports
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Auto-generated every Sunday from your check-ins + disputes the past
        7 days. Both of you see the same report.
      </p>

      {!latest ? (
        <div className="mt-8 rounded-lg border border-dashed border-input bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No reports yet. Do daily check-ins for a few days — the first
            report drops next Sunday.
          </p>
        </div>
      ) : (
        <>
          {/* Latest report — featured */}
          <article className="mt-6 rounded-lg border border-input bg-card p-6">
            <header className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {new Date(latest.period_start).toLocaleDateString()} →{" "}
                {new Date(latest.period_end).toLocaleDateString()}
              </span>
              <span>Latest</span>
            </header>

            {latest.content.themes && latest.content.themes.length > 0 && (
              <Section title="Themes this week">
                <ul className="list-disc space-y-1 pl-5">
                  {latest.content.themes.map((t, i) => <li key={i}>{t}</li>)}
                </ul>
              </Section>
            )}

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {latest.content.wins && (
                <ToneBlock tone="emerald" title="Wins">
                  <ul className="list-disc space-y-1 pl-5">
                    {latest.content.wins.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </ToneBlock>
              )}
              {latest.content.watch && (
                <ToneBlock tone="amber" title="Watch">
                  <ul className="list-disc space-y-1 pl-5">
                    {latest.content.watch.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </ToneBlock>
              )}
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {latest.content.effort_summary_a && (
                <ToneBlock tone="muted" title="Partner A — effort summary">
                  <p>{latest.content.effort_summary_a}</p>
                </ToneBlock>
              )}
              {latest.content.effort_summary_b && (
                <ToneBlock tone="muted" title="Partner B — effort summary">
                  <p>{latest.content.effort_summary_b}</p>
                </ToneBlock>
              )}
            </div>

            {latest.content.experiment && (
              <ToneBlock tone="violet" title="This week's experiment">
                <p className="font-medium">{latest.content.experiment}</p>
              </ToneBlock>
            )}
          </article>

          {/* Older reports list */}
          {reports.length > 1 && (
            <section className="mt-8">
              <h2 className="text-sm font-semibold text-muted-foreground">
                Older reports
              </h2>
              <ul className="mt-2 flex flex-col gap-1">
                {reports.slice(1).map((r) => (
                  <li
                    key={r.id}
                    className="rounded-md border border-input bg-card px-3 py-2 text-sm"
                  >
                    <details>
                      <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                        {new Date(r.period_start).toLocaleDateString()} →{" "}
                        {new Date(r.period_end).toLocaleDateString()}
                      </summary>
                      <div className="mt-2 text-xs">
                        {r.content.themes && (
                          <p>
                            <strong>Themes:</strong> {r.content.themes.join("; ")}
                          </p>
                        )}
                        {r.content.experiment && (
                          <p className="mt-1">
                            <strong>Experiment:</strong> {r.content.experiment}
                          </p>
                        )}
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <div className="mt-2 text-sm leading-relaxed">{children}</div>
    </section>
  );
}

function ToneBlock({
  tone,
  title,
  children,
}: {
  tone: "emerald" | "amber" | "violet" | "muted";
  title: string;
  children: React.ReactNode;
}) {
  const cls =
    tone === "emerald"
      ? "border-emerald-500/30 bg-emerald-500/5"
      : tone === "amber"
      ? "border-amber-500/30 bg-amber-500/5"
      : tone === "violet"
      ? "mt-4 border-violet-500/30 bg-violet-500/5"
      : "border-input bg-muted/30";
  return (
    <div className={`rounded-lg border p-4 text-sm ${cls}`}>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <div className="mt-2 leading-relaxed">{children}</div>
    </div>
  );
}
