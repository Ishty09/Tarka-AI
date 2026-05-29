"use client";

import { useEffect, useState } from "react";

interface CheckResult {
  ok: boolean;
  detail?: unknown;
  error?: string;
}

interface Snapshot {
  ok: boolean;
  generated_at: string;
  auth: { user_id: string; email?: string };
  web: {
    commit: string;
    commit_short: string;
    deployed_url: string;
    deployed_branch: string;
  };
  workers: CheckResult;
  database: { couples_invite_rls: CheckResult };
  data: { conversations: CheckResult; messages: CheckResult };
  next_steps: string[];
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${
        ok
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : "bg-red-500/10 text-red-700 dark:text-red-300"
      }`}
    >
      <span aria-hidden>{ok ? "✓" : "✗"}</span>
      {label}
    </span>
  );
}

function Section({
  title,
  status,
  children,
}: {
  title: string;
  status?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-input bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">{title}</h2>
        {status !== undefined && (
          <StatusPill ok={status} label={status ? "OK" : "FAIL"} />
        )}
      </div>
      <div className="mt-3 text-xs">{children}</div>
    </section>
  );
}

function Pre({ children }: { children: unknown }) {
  return (
    <pre className="overflow-x-auto rounded-md border border-input bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
      {typeof children === "string" ? children : JSON.stringify(children, null, 2)}
    </pre>
  );
}

export function DiagnosticsView() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/diagnostics", { cache: "no-store" });
        const body = await res.json();
        if (cancelled) return;
        if (!res.ok) {
          setError(body.error ?? `HTTP ${res.status}`);
          return;
        }
        setSnap(body as Snapshot);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <p className="mt-6 text-sm text-muted-foreground">Running probes…</p>;
  }
  if (error || !snap) {
    return (
      <div className="mt-6 rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
        Diagnostics endpoint failed: {error ?? "no snapshot"}
      </div>
    );
  }

  const overallOk =
    snap.workers.ok &&
    snap.database.couples_invite_rls.ok &&
    snap.data.conversations.ok &&
    snap.data.messages.ok;

  return (
    <div className="mt-6 flex flex-col gap-4">
      <Section title="Overall">
        <div className="flex flex-col gap-2">
          <StatusPill ok={overallOk} label={overallOk ? "All probes passed" : "One or more probes failed"} />
          <p className="text-muted-foreground">
            Generated {new Date(snap.generated_at).toLocaleString()} · Signed in
            as <span className="font-mono">{snap.auth.email}</span> (user_id{" "}
            <span className="font-mono">{snap.auth.user_id.slice(0, 8)}…</span>)
          </p>
        </div>
      </Section>

      <Section title="Web (Vercel deployment)">
        <Pre>{snap.web}</Pre>
      </Section>

      <Section title="Workers (DigitalOcean / Coolify)" status={snap.workers.ok}>
        {snap.workers.error && (
          <p className="mb-2 text-destructive">{snap.workers.error}</p>
        )}
        <Pre>{snap.workers.detail ?? "(no detail)"}</Pre>
        <p className="mt-2 text-muted-foreground">
          Check the <code>build_marker</code> field. If it&apos;s missing or older
          than the latest commit, Coolify hasn&apos;t actually picked up the new
          container — redeploy from the Coolify dashboard.
        </p>
      </Section>

      <Section
        title="Database — couples invite RLS policy"
        status={snap.database.couples_invite_rls.ok}
      >
        {snap.database.couples_invite_rls.error && (
          <p className="mb-2 text-destructive">{snap.database.couples_invite_rls.error}</p>
        )}
        <Pre>{snap.database.couples_invite_rls.detail ?? "(no detail)"}</Pre>
      </Section>

      <Section title="Your conversations" status={snap.data.conversations.ok}>
        {snap.data.conversations.error && (
          <p className="mb-2 text-destructive">{snap.data.conversations.error}</p>
        )}
        <Pre>{snap.data.conversations.detail ?? "(no detail)"}</Pre>
      </Section>

      <Section title="Your messages" status={snap.data.messages.ok}>
        {snap.data.messages.error && (
          <p className="mb-2 text-destructive">{snap.data.messages.error}</p>
        )}
        <Pre>{snap.data.messages.detail ?? "(no detail)"}</Pre>
      </Section>

      <Section title="Next steps">
        <ul className="flex list-disc flex-col gap-2 pl-5 text-muted-foreground">
          {snap.next_steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
