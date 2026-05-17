import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { markMirrorViewed } from "./actions";

// Mirror Mode (§9.4.2). Weekly summary cards, newest first. The latest is
// rendered expanded; older ones collapse to header + first paragraph of
// summary. Free-tier users can read past reports but won't get new ones
// generated (§8.1).

type Pattern = { theme: string; support: string };
type Dodge = { topic: string; observed: string };

type Report = {
  id: string;
  period_start: string;
  period_end: string;
  summary: string;
  patterns: Pattern[] | null;
  dodges: Dodge[] | null;
  generated_at: string;
  viewed_at: string | null;
};

export default async function MirrorPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";

  const { data: rowsData } = await supabase
    .from("mirror_reports")
    .select("id, period_start, period_end, summary, patterns, dodges, generated_at, viewed_at")
    .eq("user_id", user.id)
    .order("period_start", { ascending: false })
    .limit(52); // up to a year of weekly reports
  const reports = (rowsData ?? []) as unknown as Report[];

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Mirror Mode</h1>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs uppercase tracking-wide">
          {tier}
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {tier === "free"
          ? "Free tier is read-only. Upgrade to get a weekly report generated."
          : "A new report each week. It's not flattering."}
      </p>

      {reports.length === 0 ? (
        <p className="mt-10 text-sm text-muted-foreground">
          No reports yet. Your first one shows up after a week of conversations.
        </p>
      ) : (
        <ul className="mt-6 flex flex-col gap-4">
          {reports.map((report, idx) => (
            <li key={report.id}>
              <ReportCard report={report} expanded={idx === 0} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

function ReportCard({ report, expanded }: { report: Report; expanded: boolean }) {
  const patterns = report.patterns ?? [];
  const dodges = report.dodges ?? [];
  const summaryParagraphs = report.summary.split(/\n\n+/).filter(Boolean);

  return (
    <details
      open={expanded}
      className="group rounded-md border border-input bg-background p-4 shadow-sm"
    >
      <summary className="flex cursor-pointer items-center justify-between gap-3 text-sm">
        <div className="flex flex-col">
          <span className="font-medium">
            {formatDate(report.period_start)} – {formatDate(report.period_end)}
          </span>
          <span className="text-xs text-muted-foreground">
            {summaryParagraphs[0]?.slice(0, 120)}
            {(summaryParagraphs[0]?.length ?? 0) > 120 ? "…" : ""}
          </span>
        </div>
        {!report.viewed_at && (
          <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-700">
            new
          </span>
        )}
      </summary>

      <div className="mt-4 flex flex-col gap-4 text-sm">
        {summaryParagraphs.map((p, i) => (
          <p key={i} className="leading-relaxed">{p}</p>
        ))}

        {patterns.length > 0 && (
          <section className="flex flex-col gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Patterns
            </h2>
            <ul className="flex flex-col gap-2">
              {patterns.map((p, i) => (
                <li key={i} className="rounded-md border border-input bg-muted/30 p-2 text-xs">
                  <span className="font-medium">{p.theme}</span>
                  <p className="mt-1 text-muted-foreground">{p.support}</p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {dodges.length > 0 && (
          <section className="flex flex-col gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Dodges
            </h2>
            <ul className="flex flex-col gap-2">
              {dodges.map((d, i) => (
                <li key={i} className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs">
                  <span className="font-medium">{d.topic}</span>
                  <p className="mt-1 text-muted-foreground">{d.observed}</p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {!report.viewed_at && (
          <form action={markMirrorViewed}>
            <input type="hidden" name="id" value={report.id} />
            <button
              type="submit"
              className="self-start rounded-md border border-input bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              Mark as read
            </button>
          </form>
        )}
      </div>
    </details>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
