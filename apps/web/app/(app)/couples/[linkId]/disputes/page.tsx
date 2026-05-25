import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";

interface PageProps {
  params: Promise<{ linkId: string }>;
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  awaiting: { label: "Awaiting", cls: "bg-amber-500/20 text-amber-900 dark:text-amber-200" },
  arbitrating: { label: "Arbitrating…", cls: "bg-blue-500/20 text-blue-900 dark:text-blue-200" },
  arbitrated: { label: "Verdict ready", cls: "bg-emerald-500/20 text-emerald-900 dark:text-emerald-200" },
  resolved: { label: "Resolved", cls: "bg-muted text-muted-foreground" },
};

export default async function DisputesIndexPage({ params }: PageProps) {
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

  type DisputeRow = {
    id: string;
    title: string;
    status: string;
    created_at: string;
    perspective_a_user_id: string | null;
    perspective_a_submitted_at: string | null;
    perspective_b_user_id: string | null;
    perspective_b_submitted_at: string | null;
  };
  const { data: rawDisputes } = await supabase
    .from("couple_disputes")
    .select(
      "id, title, status, created_at, " +
        "perspective_a_user_id, perspective_a_submitted_at, " +
        "perspective_b_user_id, perspective_b_submitted_at"
    )
    .eq("couple_link_id", linkId)
    .order("created_at", { ascending: false });
  const disputes: DisputeRow[] = (rawDisputes ?? []) as unknown as DisputeRow[];

  const isA = user.id === link.user_a;

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <Link
        href={`/couples/${linkId}`}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ← Back to couple
      </Link>
      <div className="mt-2 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Disputes</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Each of you writes your side. When both submit, Quarrel produces
            a verdict you see together.
          </p>
        </div>
        <Link
          href={`/couples/${linkId}/disputes/new`}
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          New dispute
        </Link>
      </div>

      {disputes.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-input bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No disputes yet. When the next fight happens, this is where it
            goes.
          </p>
          <Link
            href={`/couples/${linkId}/disputes/new`}
            className="mt-3 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            Start one now
          </Link>
        </div>
      ) : (
        <ul className="mt-6 flex flex-col gap-2">
          {disputes.map((d) => {
            const meta = STATUS_META[d.status] ?? STATUS_META.awaiting;
            const myTurn =
              d.status === "awaiting" &&
              ((isA && !d.perspective_a_submitted_at) ||
                (!isA && !d.perspective_b_submitted_at));
            return (
              <li key={d.id}>
                <Link
                  href={`/couples/${linkId}/disputes/${d.id}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-input bg-card px-4 py-3 text-sm shadow-sm transition hover:border-primary/40 hover:bg-accent"
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium">{d.title}</span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(d.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {myTurn && (
                      <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                        Your turn
                      </span>
                    )}
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${meta.cls}`}
                    >
                      {meta.label}
                    </span>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
