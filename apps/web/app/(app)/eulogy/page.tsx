import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { markEulogyViewed } from "./actions";

// Eulogy Test (§9.4.3). Quarterly text-only report rendered with somber
// styling — wide leading, slate background, serif body. Free tier has no
// generated reports yet (§8.1), so a free user sees the empty state.

type Report = {
  id: string;
  quarter: string;
  content: string;
  generated_at: string;
  viewed_at: string | null;
};

export default async function EulogyPage() {
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
    .from("eulogy_reports")
    .select("id, quarter, content, generated_at, viewed_at")
    .eq("user_id", user.id)
    .order("quarter", { ascending: false })
    .limit(20);
  const reports = (rowsData ?? []) as unknown as Report[];

  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">The Eulogy</h1>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs uppercase tracking-wide">
          {tier}
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {tier === "free"
          ? "Eulogies are generated quarterly on Pro and Max."
          : "One eulogy per quarter. Brutal but caring."}
      </p>

      {reports.length === 0 ? (
        <p className="mt-10 text-sm text-muted-foreground">
          No eulogies yet. Your first one shows up after your first full quarter.
        </p>
      ) : (
        <div className="mt-8 flex flex-col gap-6">
          {reports.map((report, idx) => (
            <EulogyCard key={report.id} report={report} expanded={idx === 0} />
          ))}
        </div>
      )}
    </main>
  );
}

function EulogyCard({ report, expanded }: { report: Report; expanded: boolean }) {
  return (
    <details
      open={expanded}
      className="group rounded-md border border-input bg-muted/20 shadow-sm"
    >
      <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm">
        <div className="flex flex-col">
          <span className="font-medium tracking-tight">{report.quarter}</span>
          <span className="text-xs text-muted-foreground">
            Generated {new Date(report.generated_at).toLocaleDateString()}
          </span>
        </div>
        {!report.viewed_at && (
          <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-700">
            unread
          </span>
        )}
      </summary>

      <div className="border-t border-input/60 px-6 py-8">
        <article className="font-serif text-base leading-loose text-foreground/90 whitespace-pre-wrap">
          {report.content}
        </article>

        {!report.viewed_at && (
          <form action={markEulogyViewed} className="mt-6">
            <input type="hidden" name="id" value={report.id} />
            <button
              type="submit"
              className="rounded-md border border-input bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              Mark as read
            </button>
          </form>
        )}
      </div>
    </details>
  );
}
