"use client";

import { useState } from "react";
import Link from "next/link";

interface WrongReason {
  reason: string;
  argument: string;
}

interface DecisionKillerResponse {
  conversation_id: string;
  assistant_message_id: number | null;
  reasons_wrong: WrongReason[];
  one_reason_right: string;
  actual_avoidance: string;
}

interface QuotaExceeded {
  tier: string;
  limit: number;
  used: number;
  reset_at: string;
  upgrade_url: string | null;
}

const MIN = 20;
const MAX = 4000;

export function DecisionKillerForm() {
  const [decision, setDecision] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaExceeded | null>(null);
  const [result, setResult] = useState<DecisionKillerResponse | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending || decision.trim().length < MIN) return;
    setError(null);
    setQuota(null);
    setResult(null);
    setPending(true);
    try {
      const res = await fetch("/api/tools/decision-killer", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      if (res.status === 429) {
        const body = await res.json();
        setQuota((body.detail ?? body) as QuotaExceeded);
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(
          body.detail?.reason ?? body.detail?.error ?? body.error ?? `Request failed (${res.status})`,
        );
        return;
      }
      setResult((await res.json()) as DecisionKillerResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label htmlFor="decision" className="text-sm font-medium">
          Your decision
        </label>
        <textarea
          id="decision"
          required
          minLength={MIN}
          maxLength={MAX}
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          rows={8}
          placeholder="The decision you're about to make. Be specific — vague decisions get vague pushback."
          className="resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {decision.length} / {MAX}
          </span>
          <button
            type="submit"
            disabled={pending || decision.trim().length < MIN}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "Pressuring..." : "Kill it"}
          </button>
        </div>
      </form>

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

      {result && <DecisionKillerResult result={result} />}
    </div>
  );
}

function DecisionKillerResult({ result }: { result: DecisionKillerResponse }) {
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-md border border-red-500/30 bg-red-500/5 p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-red-700/90">
          3 Reasons This Is Wrong
        </h2>
        <ol className="mt-3 flex flex-col gap-3">
          {result.reasons_wrong.map((r, i) => (
            <li key={i} className="text-sm">
              <span className="font-medium">{i + 1}. {r.reason}</span>
              <p className="mt-1 text-muted-foreground">{r.argument}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-emerald-700/90">
          1 Reason It Might Be Right
        </h2>
        <p className="mt-2 text-sm leading-relaxed">{result.one_reason_right}</p>
      </section>

      <section className="rounded-md border border-amber-500/40 bg-amber-500/10 p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-700/90">
          What You&apos;re Actually Avoiding
        </h2>
        <p className="mt-2 text-sm italic leading-relaxed">{result.actual_avoidance}</p>
      </section>

      <div className="text-xs text-muted-foreground">
        Saved to{" "}
        <Link className="underline" href={`/chat/${result.conversation_id}`}>
          a conversation
        </Link>{" "}
        you can keep arguing in.
      </div>
    </div>
  );
}
