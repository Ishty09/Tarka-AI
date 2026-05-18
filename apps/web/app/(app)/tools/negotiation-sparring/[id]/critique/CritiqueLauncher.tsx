"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface CritiqueResponse {
  strengths: string[];
  weaknesses: string[];
  alternative: string;
}

interface QuotaExceeded {
  tier: string;
  limit: number;
  used: number;
  reset_at: string;
  upgrade_url: string | null;
}

export function CritiqueLauncher({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaExceeded | null>(null);
  const [result, setResult] = useState<CritiqueResponse | null>(null);

  async function onClick() {
    if (pending) return;
    setPending(true);
    setError(null);
    setQuota(null);
    try {
      const res = await fetch("/api/tools/negotiation-sparring/critique", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ conversation_id: conversationId }),
      });
      if (res.status === 429) {
        const body = await res.json();
        setQuota((body.detail ?? body) as QuotaExceeded);
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(
          body.detail?.error ?? body.detail ?? body.error ?? `Request failed (${res.status})`,
        );
        return;
      }
      setResult((await res.json()) as CritiqueResponse);
      // Refresh so the cached critique renders the next time the user lands here.
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setPending(false);
    }
  }

  if (result) {
    return (
      <div className="mt-6 flex flex-col gap-4">
        <Panel title="Strengths" items={result.strengths} tone="positive" />
        <Panel title="Weaknesses" items={result.weaknesses} tone="negative" />
        <section className="rounded-md border border-primary/40 bg-primary/5 p-4 shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-primary/90">
            What to try next time
          </h2>
          <p className="mt-2 text-sm leading-relaxed">{result.alternative}</p>
        </section>
      </div>
    );
  }

  return (
    <div className="mt-6 flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Generating the critique reads every user turn in this session and asks
        the AI to grade you. Counts as 1 message.
      </p>
      <button
        type="button"
        onClick={onClick}
        disabled={pending}
        className="self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Grading…" : "Grade me"}
      </button>
      {quota && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          You hit your {quota.tier} daily message limit ({quota.used}/{quota.limit}).
          Resets {new Date(quota.reset_at).toLocaleString()}.{" "}
          {quota.upgrade_url && (
            <a href={quota.upgrade_url} className="underline">Upgrade</a>
          )}
        </div>
      )}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

function Panel({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "positive" | "negative";
}) {
  const border = tone === "positive" ? "border-emerald-500/30 bg-emerald-500/5" : "border-red-500/30 bg-red-500/5";
  const heading = tone === "positive" ? "text-emerald-700/90" : "text-red-700/90";
  return (
    <section className={`rounded-md border ${border} p-4 shadow-sm`}>
      <h2 className={`text-sm font-semibold uppercase tracking-wide ${heading}`}>{title}</h2>
      <ol className="mt-2 flex flex-col gap-2 text-sm">
        {items.map((item, i) => (
          <li key={i}>
            <span className="font-medium">{i + 1}.</span> {item}
          </li>
        ))}
      </ol>
    </section>
  );
}
