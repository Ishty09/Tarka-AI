"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface Scenario {
  slug: string;
  title: string;
  blurb: string;
  counterparty: string;
}

export function ScenarioPicker() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/tools/negotiation-sparring", { method: "GET" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Failed to load scenarios (${res.status})`);
        return res.json();
      })
      .then((body) => {
        if (alive) setScenarios(body.scenarios as Scenario[]);
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : "Failed to load");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  async function start(slug: string) {
    setSubmitting(slug);
    setError(null);
    try {
      const res = await fetch("/api/tools/negotiation-sparring", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ scenario_slug: slug }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          body.detail?.error ?? body.detail ?? body.error ?? `Failed (${res.status})`,
        );
      }
      const body = await res.json();
      router.push(`/chat/${body.conversation_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start");
    } finally {
      setSubmitting(null);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading scenarios…</p>;
  }
  if (scenarios.length === 0 && error) {
    return <p role="alert" className="text-sm text-destructive">{error}</p>;
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {scenarios.map((s) => (
        <button
          key={s.slug}
          type="button"
          onClick={() => start(s.slug)}
          disabled={submitting !== null}
          className="flex flex-col gap-1 rounded-md border border-input bg-background p-4 text-left shadow-sm hover:bg-accent disabled:opacity-50"
        >
          <span className="text-sm font-medium">{s.title}</span>
          <span className="text-xs text-muted-foreground">vs {s.counterparty}</span>
          <span className="mt-1 text-xs leading-relaxed">{s.blurb}</span>
          {submitting === s.slug && (
            <span className="mt-2 text-xs text-muted-foreground">Starting…</span>
          )}
        </button>
      ))}
      {error && (
        <p role="alert" className="col-span-full text-sm text-destructive">{error}</p>
      )}
    </div>
  );
}
