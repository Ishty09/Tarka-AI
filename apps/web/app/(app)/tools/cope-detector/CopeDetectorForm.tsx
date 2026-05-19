"use client";

import { useState } from "react";
import Link from "next/link";
import { CopyButton } from "../_components/CopyButton";

interface CopeDetectorResponse {
  conversation_id: string;
  assistant_message_id: number | null;
  telling_yourself: string;
  actually_avoiding: string;
  unasked_question: string;
}

interface QuotaExceeded {
  tier: string;
  limit: number;
  used: number;
  reset_at: string;
  upgrade_url: string | null;
}

const MIN = 15;
const MAX = 4000;

interface FormProps {
  examples?: string[];
}

export function CopeDetectorForm({ examples = [] }: FormProps) {
  const [rationalization, setRationalization] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaExceeded | null>(null);
  const [result, setResult] = useState<CopeDetectorResponse | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending || rationalization.trim().length < MIN) return;
    setError(null);
    setQuota(null);
    setResult(null);
    setPending(true);
    try {
      const res = await fetch("/api/tools/cope-detector", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ rationalization }),
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
      setResult((await res.json()) as CopeDetectorResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label htmlFor="rationalization" className="text-sm font-medium">
          The story you&apos;re telling yourself
        </label>
        <textarea
          id="rationalization"
          required
          minLength={MIN}
          maxLength={MAX}
          value={rationalization}
          onChange={(e) => setRationalization(e.target.value)}
          rows={6}
          placeholder='e.g. "I&apos;ll start the new thing once I finish wrapping up the old one — it&apos;s only fair to the team."'
          className="resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {rationalization.length} / {MAX}
          </span>
          <button
            type="submit"
            disabled={pending || rationalization.trim().length < MIN}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "Reading..." : "Detect"}
          </button>
        </div>
      </form>

      {!result && !pending && examples.length > 0 && rationalization.length === 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Try one of these
          </p>
          <div className="flex flex-col gap-2">
            {examples.map((ex, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setRationalization(ex)}
                className="rounded-md border border-input bg-background px-3 py-2 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
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

      {result && <CopeDetectorResult result={result} />}
    </div>
  );
}

function CopeDetectorResult({ result }: { result: CopeDetectorResponse }) {
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-md border border-input bg-muted/30 p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            What You&apos;re Telling Yourself
          </h2>
          <CopyButton text={result.telling_yourself} />
        </div>
        <p className="mt-2 text-sm leading-relaxed">{result.telling_yourself}</p>
      </section>

      <section className="rounded-md border border-amber-500/40 bg-amber-500/10 p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-700/90">
            What You&apos;re Actually Avoiding
          </h2>
          <CopyButton text={result.actually_avoiding} />
        </div>
        <p className="mt-2 text-sm leading-relaxed">{result.actually_avoiding}</p>
      </section>

      <section className="rounded-md border border-primary/40 bg-primary/5 p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-primary/90">
            The Question You&apos;re Not Asking
          </h2>
          <CopyButton text={result.unasked_question} />
        </div>
        <p className="mt-2 text-base italic leading-relaxed">{result.unasked_question}</p>
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
