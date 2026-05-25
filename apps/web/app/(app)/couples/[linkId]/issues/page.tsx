import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { NewIssueForm } from "./NewIssueForm";
import { IssueRow } from "./IssueRow";

interface PageProps {
  params: Promise<{ linkId: string }>;
}

interface Issue {
  id: string;
  theme: string;
  description: string | null;
  status: "discussed" | "agreed" | "resolved" | "recurring";
  severity: number;
  source: string;
  first_raised_at: string;
  last_discussed_at: string;
  resolved_at: string | null;
  recurrence_count: number;
  notes: string | null;
}

const STATUS_GROUPS: { key: Issue["status"]; label: string }[] = [
  { key: "recurring", label: "🔁 Recurring (needs decision)" },
  { key: "discussed", label: "💬 Discussed" },
  { key: "agreed", label: "🤝 Agreed" },
  { key: "resolved", label: "✓ Resolved" },
];

export default async function CoupleIssuesPage({ params }: PageProps) {
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

  const { data: rawIssues } = await supabase
    .from("couple_issues")
    .select(
      "id, theme, description, status, severity, source, first_raised_at, last_discussed_at, resolved_at, recurrence_count, notes"
    )
    .eq("couple_link_id", linkId)
    .order("severity", { ascending: false })
    .order("last_discussed_at", { ascending: false });
  const issues: Issue[] = (rawIssues ?? []) as unknown as Issue[];

  const grouped = new Map<Issue["status"], Issue[]>();
  for (const s of STATUS_GROUPS) grouped.set(s.key, []);
  for (const i of issues) grouped.get(i.status)?.push(i);

  // Flag stale issues: discussed/agreed older than 30 days.
  const thirtyDaysAgo = Date.now() - 30 * 24 * 60 * 60 * 1000;
  const staleCount = issues.filter(
    (i) =>
      (i.status === "discussed" || i.status === "agreed") &&
      new Date(i.last_discussed_at).getTime() < thirtyDaysAgo,
  ).length;

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <Link
        href={`/couples/${linkId}`}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ← Back to couple
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Open issues</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Themes you two keep coming back to. Track what&apos;s discussed,
        what&apos;s agreed, what&apos;s actually resolved.
      </p>

      {staleCount > 0 && (
        <div className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs">
          {staleCount} issue{staleCount > 1 ? "s" : ""} haven&apos;t been
          revisited in 30+ days. They&apos;ll show up in your next weekly
          report.
        </div>
      )}

      <section className="mt-6 rounded-lg border border-input bg-card p-4">
        <h2 className="text-sm font-semibold">Add an issue</h2>
        <NewIssueForm linkId={linkId} />
      </section>

      {STATUS_GROUPS.map(({ key, label }) => {
        const group = grouped.get(key) ?? [];
        if (group.length === 0) return null;
        return (
          <section key={key} className="mt-6">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {label} · {group.length}
            </h2>
            <ul className="flex flex-col gap-2">
              {group.map((issue) => (
                <li key={issue.id}>
                  <IssueRow issue={issue} />
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      {issues.length === 0 && (
        <div className="mt-8 rounded-lg border border-dashed border-input bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No issues tracked yet. Add the first one above, or wait — they get
            auto-extracted from disputes as you use them.
          </p>
        </div>
      )}
    </main>
  );
}
