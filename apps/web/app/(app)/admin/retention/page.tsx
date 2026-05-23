import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

// §27 step 73 — 7-day retention dashboard. Reads the cohort_retention
// view (created in 20260524120100_cohort_retention.sql). The layout
// already gates on is_admin; we don't re-check here but RLS on the
// underlying beta_invites table is the source of truth.
//
// §28 gate: retention_rate ≥ 0.30 on the launch cohort.

const LAUNCH_GATE = 0.3;

interface CohortRow {
  cohort_tag: string;
  invited: number;
  sent: number;
  signed_up: number;
  retained_d2_d7: number;
  activation_rate: number;
  retention_rate: number;
}

function percent(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

export default async function RetentionPage() {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data, error } = await supabase
    .from("cohort_retention")
    .select(
      "cohort_tag, invited, sent, signed_up, retained_d2_d7, activation_rate, retention_rate",
    )
    .order("cohort_tag", { ascending: true });

  const rows = (data ?? []) as CohortRow[];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Cohort retention</h2>
        <p className="text-sm text-muted-foreground">
          §28 launch gate: <strong>{percent(LAUNCH_GATE)}</strong> of signed-up
          invitees send ≥ 1 message in the 1–7 day window after signup.
        </p>
      </header>

      {error ? (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          Failed to load retention data: {error.message}
        </p>
      ) : null}

      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No cohorts yet. Send invites via{" "}
          <code className="rounded bg-muted px-1 py-0.5">pnpm invite:beta</code> and
          they&apos;ll appear here once they sign up.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Cohort
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Invited
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Sent
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Signed up
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Activation
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Retained D2-D7
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Retention
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const gateMet = row.retention_rate >= LAUNCH_GATE;
                return (
                  <tr key={row.cohort_tag} className="border-b last:border-b-0">
                    <th
                      scope="row"
                      className="px-4 py-3 text-left font-medium text-foreground"
                    >
                      {row.cohort_tag}
                    </th>
                    <td className="px-4 py-3 text-muted-foreground">{row.invited}</td>
                    <td className="px-4 py-3 text-muted-foreground">{row.sent}</td>
                    <td className="px-4 py-3 text-muted-foreground">{row.signed_up}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {percent(row.activation_rate)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{row.retained_d2_d7}</td>
                    <td
                      className={`px-4 py-3 font-medium ${
                        gateMet
                          ? "text-emerald-700"
                          : row.signed_up === 0
                          ? "text-muted-foreground"
                          : "text-destructive"
                      }`}
                    >
                      {percent(row.retention_rate)}
                      {row.signed_up > 0 ? (
                        <span className="ml-2 text-xs">
                          {gateMet ? "✓ gate met" : "below gate"}
                        </span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <details className="rounded-lg border bg-card p-4 text-sm">
        <summary className="cursor-pointer text-sm font-medium">
          How this is computed
        </summary>
        <p className="mt-3 text-muted-foreground">
          The <code>cohort_retention</code> SQL view joins{" "}
          <code>beta_invites</code> against <code>messages</code>: a signed-up
          invitee is "retained D2-D7" when they sent ≥ 1{" "}
          <code>role = &apos;user&apos;</code> message between 1 and 7 days
          after <code>signed_up_at</code>. Activation rate is{" "}
          <code>signed_up / invited</code>; retention rate is{" "}
          <code>retained_d2_d7 / signed_up</code>.
        </p>
        <p className="mt-2 text-muted-foreground">
          See <code>infra/runbooks/beta-cohort.md</code> for the post-mortem
          template and the operational steps to invite a new cohort.
        </p>
      </details>
    </div>
  );
}
