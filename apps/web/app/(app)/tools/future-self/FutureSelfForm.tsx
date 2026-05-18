"use client";

import { useState } from "react";
import Link from "next/link";

interface FutureSelfResponse {
  conversation_id: string;
  assistant_message_id: number | null;
  message: string;
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

export function FutureSelfForm() {
  const [decision, setDecision] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaExceeded | null>(null);
  const [result, setResult] = useState<FutureSelfResponse | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending || decision.trim().length < MIN) return;
    setError(null);
    setQuota(null);
    setResult(null);
    setPending(true);
    try {
      const res = await fetch("/api/tools/future-self", {
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
      setResult((await res.json()) as FutureSelfResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {!result && (
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <label htmlFor="decision" className="text-sm font-medium">
            The decision you&apos;re considering
          </label>
          <textarea
            id="decision"
            required
            minLength={MIN}
            maxLength={MAX}
            value={decision}
            onChange={(e) => setDecision(e.target.value)}
            rows={8}
            placeholder="What are you about to do, or not do? Be specific. The more detail, the sharper the call."
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
              {pending ? "Calling..." : "Call future-me"}
            </button>
          </div>
        </form>
      )}

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

      {result && (
        <FutureSelfResult
          decision={decision}
          message={result.message}
          conversationId={result.conversation_id}
        />
      )}
    </div>
  );
}

function FutureSelfResult({
  decision,
  message,
  conversationId,
}: {
  decision: string;
  message: string;
  conversationId: string;
}) {
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-md border border-input bg-muted/30 p-4 shadow-sm">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          You wrote
        </h2>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{decision}</p>
      </section>

      <section className="rounded-md border border-primary/40 bg-primary/5 p-5 shadow-sm">
        <div className="flex items-center gap-3">
          <div
            aria-hidden
            className="flex size-10 items-center justify-center rounded-full bg-muted text-base"
          >
            🪞
          </div>
          <div>
            <h2 className="text-sm font-semibold">You, at 80</h2>
            <p className="text-xs text-muted-foreground">
              Wise, regretful, urgent. Already knows the cost.
            </p>
          </div>
        </div>
        <p className="mt-4 whitespace-pre-wrap font-serif text-base leading-loose text-foreground/90">
          {message}
        </p>
      </section>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Push back. Argue with future-you in the conversation.</span>
        <Link
          href={`/chat/${conversationId}`}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
        >
          Continue →
        </Link>
      </div>
    </div>
  );
}
