import Link from "next/link";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import { PerspectiveForm } from "./PerspectiveForm";
import { ResolveButton } from "./ResolveButton";

interface PageProps {
  params: Promise<{ linkId: string; disputeId: string }>;
}

interface Verdict {
  summary?: string;
  who_escalated_first?: "a" | "b" | "both" | "unclear";
  what_a_actually_wanted?: string;
  what_b_actually_wanted?: string;
  patterns_detected?: string[];
  advice_for_a?: string[];
  advice_for_b?: string[];
  what_to_do_next?: string;
  confidence?: number;
}

export default async function DisputeDetailPage({ params }: PageProps) {
  const { linkId, disputeId } = await params;

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

  type DisputeDetail = {
    id: string;
    title: string;
    status: string;
    perspective_a_user_id: string | null;
    perspective_a_text: string | null;
    perspective_a_submitted_at: string | null;
    perspective_b_user_id: string | null;
    perspective_b_text: string | null;
    perspective_b_submitted_at: string | null;
    arbitration: unknown;
    arbitrated_at: string | null;
    resolved_at: string | null;
  };
  const { data: rawDispute } = await supabase
    .from("couple_disputes")
    .select(
      "id, title, status, " +
        "perspective_a_user_id, perspective_a_text, perspective_a_submitted_at, " +
        "perspective_b_user_id, perspective_b_text, perspective_b_submitted_at, " +
        "arbitration, arbitrated_at, resolved_at"
    )
    .eq("id", disputeId)
    .maybeSingle();
  const d = rawDispute as unknown as DisputeDetail | null;
  if (!d) redirect(`/couples/${linkId}`);

  const isA = user.id === link.user_a;
  const myText = isA ? d.perspective_a_text : d.perspective_b_text;
  const theirText = isA ? d.perspective_b_text : d.perspective_a_text;
  const mySubmitted = Boolean(myText);
  const theirSubmitted = Boolean(theirText);
  const bothSubmitted = mySubmitted && theirSubmitted;
  const arbitration: Verdict | null = (d.arbitration as Verdict | null) ?? null;

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <Link
        href={`/couples/${linkId}`}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ← Back to couple
      </Link>

      <div className="mt-2 flex items-start justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{d.title}</h1>
        <StatusPill status={d.status} />
      </div>

      {/* No perspective yet from this user → show form */}
      {!mySubmitted && (
        <section className="mt-6 rounded-lg border border-input bg-card p-4">
          <h2 className="text-sm font-semibold">Add your perspective</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Your partner already submitted. Write your side. After you submit,
            Quarrel produces a verdict you both see at the same time. You
            cannot read theirs first — that&apos;s on purpose.
          </p>
          <PerspectiveForm disputeId={disputeId} />
        </section>
      )}

      {/* Both submitted but no verdict yet */}
      {bothSubmitted && d.status !== "arbitrated" && d.status !== "resolved" && (
        <section className="mt-6 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
          <p className="font-medium">Arbitration in progress…</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Both perspectives are in. Refresh in ~10s — the verdict appears
            when the AI is done.
          </p>
        </section>
      )}

      {/* Waiting on partner */}
      {mySubmitted && !theirSubmitted && (
        <section className="mt-6 rounded-lg border border-input bg-card p-4 text-sm">
          <p className="font-medium">Waiting on your partner.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            You submitted at{" "}
            {d.perspective_a_user_id === user.id
              ? new Date(d.perspective_a_submitted_at!).toLocaleString()
              : new Date(d.perspective_b_submitted_at!).toLocaleString()}
            . Once they submit, the verdict generates automatically.
          </p>
        </section>
      )}

      {/* Verdict */}
      {arbitration && (
        <ArbitrationView
          verdict={arbitration}
          aText={d.perspective_a_text ?? ""}
          bText={d.perspective_b_text ?? ""}
          isCurrentUserA={isA}
        />
      )}

      {/* Resolve CTA */}
      {arbitration && d.status === "arbitrated" && (
        <div className="mt-6">
          <ResolveButton disputeId={disputeId} />
        </div>
      )}

      {d.status === "resolved" && (
        <p className="mt-6 text-sm text-emerald-600 dark:text-emerald-400">
          Marked resolved {d.resolved_at && new Date(d.resolved_at).toLocaleDateString()}
        </p>
      )}
    </main>
  );
}

function StatusPill({ status }: { status: string }) {
  const labels: Record<string, { label: string; cls: string }> = {
    awaiting: { label: "Awaiting", cls: "bg-amber-500/20 text-amber-900 dark:text-amber-200" },
    arbitrating: { label: "Arbitrating", cls: "bg-blue-500/20 text-blue-900 dark:text-blue-200" },
    arbitrated: { label: "Verdict ready", cls: "bg-emerald-500/20 text-emerald-900 dark:text-emerald-200" },
    resolved: { label: "Resolved", cls: "bg-muted text-muted-foreground" },
  };
  const meta = labels[status] ?? labels.awaiting;
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${meta.cls}`}
    >
      {meta.label}
    </span>
  );
}

function ArbitrationView({
  verdict,
  aText,
  bText,
  isCurrentUserA,
}: {
  verdict: Verdict;
  aText: string;
  bText: string;
  isCurrentUserA: boolean;
}) {
  const confidence = verdict.confidence ?? 0;
  const conf =
    confidence >= 7
      ? "text-emerald-600"
      : confidence >= 4
      ? "text-amber-600"
      : "text-muted-foreground";
  const escalator = verdict.who_escalated_first ?? "unclear";
  const escalatorLabel =
    escalator === "a"
      ? "Partner A escalated first"
      : escalator === "b"
      ? "Partner B escalated first"
      : escalator === "both"
      ? "Both escalated"
      : "Unclear who escalated";

  return (
    <section className="mt-6 space-y-4">
      <div className="rounded-lg border border-input bg-card p-4">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Verdict</span>
          <span className={`font-mono ${conf}`}>
            Confidence {confidence}/10
          </span>
        </div>
        <p className="mt-2 text-sm leading-relaxed">{verdict.summary}</p>
        <p className="mt-2 text-xs font-medium text-muted-foreground">{escalatorLabel}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-input bg-card p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            What you actually wanted
          </h3>
          <p className="mt-2 text-sm leading-relaxed">
            {isCurrentUserA
              ? verdict.what_a_actually_wanted
              : verdict.what_b_actually_wanted}
          </p>
        </div>
        <div className="rounded-lg border border-input bg-card p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            What your partner actually wanted
          </h3>
          <p className="mt-2 text-sm leading-relaxed">
            {isCurrentUserA
              ? verdict.what_b_actually_wanted
              : verdict.what_a_actually_wanted}
          </p>
        </div>
      </div>

      {verdict.patterns_detected && verdict.patterns_detected.length > 0 && (
        <div className="rounded-lg border border-input bg-card p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Pattern{verdict.patterns_detected.length > 1 ? "s" : ""} detected
          </h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {verdict.patterns_detected.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
            For you
          </h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {(isCurrentUserA ? verdict.advice_for_a : verdict.advice_for_b)?.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300">
            For your partner
          </h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {(isCurrentUserA ? verdict.advice_for_b : verdict.advice_for_a)?.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="rounded-lg border border-input bg-primary/5 p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          In the next 24 hours
        </h3>
        <p className="mt-2 text-sm font-medium">{verdict.what_to_do_next}</p>
      </div>

      <details className="rounded-lg border border-input bg-card p-4 text-sm">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Read both perspectives
        </summary>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div>
            <p className="text-xs font-medium text-muted-foreground">Partner A</p>
            <p className="mt-1 whitespace-pre-wrap text-sm">{aText}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Partner B</p>
            <p className="mt-1 whitespace-pre-wrap text-sm">{bText}</p>
          </div>
        </div>
      </details>
    </section>
  );
}
