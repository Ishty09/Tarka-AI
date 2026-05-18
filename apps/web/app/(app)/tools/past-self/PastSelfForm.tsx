"use client";

import { useState } from "react";
import Link from "next/link";

interface PastSelfResponse {
  conversation_id: string;
  assistant_message_id: number | null;
  rebuttal: string;
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

export function PastSelfForm() {
  const [pastContent, setPastContent] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaExceeded | null>(null);
  const [result, setResult] = useState<PastSelfResponse | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending || pastContent.trim().length < MIN) return;
    setError(null);
    setQuota(null);
    setResult(null);
    setPending(true);
    try {
      const res = await fetch("/api/tools/past-self", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ past_content: pastContent }),
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
      setResult((await res.json()) as PastSelfResponse);
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
          <label htmlFor="past_content" className="text-sm font-medium">
            What past-you wrote
          </label>
          <textarea
            id="past_content"
            required
            minLength={MIN}
            maxLength={MAX}
            value={pastContent}
            onChange={(e) => setPastContent(e.target.value)}
            rows={10}
            placeholder="Paste it raw — journal entry, tweet, DM, doc. The dates and context don't matter; the stance does."
            className="resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {pastContent.length} / {MAX}
            </span>
            <button
              type="submit"
              disabled={pending || pastContent.trim().length < MIN}
              className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
            >
              {pending ? "Arguing..." : "Argue against past-me"}
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
        <SplitView
          past={pastContent}
          rebuttal={result.rebuttal}
          conversationId={result.conversation_id}
        />
      )}
    </div>
  );
}

function SplitView({
  past,
  rebuttal,
  conversationId,
}: {
  past: string;
  rebuttal: string;
  conversationId: string;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-md border border-input bg-muted/30 p-4 shadow-sm">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Past-you wrote
          </h2>
          <pre className="mt-3 whitespace-pre-wrap font-serif text-sm leading-relaxed text-foreground/90">
            {past}
          </pre>
        </section>
        <section className="rounded-md border border-primary/40 bg-primary/5 p-4 shadow-sm">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-primary/90">
            Present-AI argues
          </h2>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{rebuttal}</p>
        </section>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>You are the judge. Which version was right?</span>
        <Link
          href={`/chat/${conversationId}`}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
        >
          Continue arguing →
        </Link>
      </div>
    </div>
  );
}
