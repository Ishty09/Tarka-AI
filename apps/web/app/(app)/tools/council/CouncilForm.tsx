"use client";

import { useState } from "react";

interface CouncilReply {
  slug: string;
  text: string | null;
  error: string | null;
}

interface Verdict {
  conditions_for: string[];
  conditions_against: string[];
  missing_information: string[];
  confidence: number;
  verdict: string;
}

interface CouncilResponse {
  conversation_id: string;
  assistant_message_id: number | null;
  replies: CouncilReply[];
  verdict: Verdict;
}

interface QuotaExceeded {
  tier: string;
  limit: number;
  used: number;
  reset_at: string;
  upgrade_url: string | null;
}

const COUNCIL_LABELS: Record<string, string> = {
  the_stoic: "The Stoic",
  the_economist: "The Economist",
  the_therapist: "The Therapist",
  the_skeptic: "The Skeptic",
  the_insider: "The Insider",
};

export function CouncilForm() {
  const [dilemma, setDilemma] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaExceeded | null>(null);
  const [result, setResult] = useState<CouncilResponse | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;
    setError(null);
    setQuota(null);
    setResult(null);
    setPending(true);
    try {
      const res = await fetch("/api/tools/council", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ dilemma }),
      });
      if (res.status === 429) {
        const body = await res.json();
        const detail = body.detail ?? body;
        setQuota(detail as QuotaExceeded);
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        // Workers' /tools/council returns 502 with detail.first_cause
        // (e.g. "rate_limit_exceeded", "model_not_found") when every
        // councilor LLM call fails. Surface it so the user knows
        // whether to retry, wait, or escalate.
        const cause = body.detail?.first_cause;
        const reason = body.detail?.reason ?? body.detail?.error;
        if (res.status === 502 && cause) {
          setError(
            `The council couldn't be reached. Upstream said: ${cause}. ` +
            "Try again in a minute — if it keeps failing, contact support.",
          );
        } else {
          setError(
            reason ?? body.detail ?? body.error ?? `Request failed (${res.status})`,
          );
        }
        return;
      }
      const data = (await res.json()) as CouncilResponse;
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label htmlFor="dilemma" className="text-sm font-medium">
          Your dilemma
        </label>
        <textarea
          id="dilemma"
          name="dilemma"
          required
          minLength={10}
          maxLength={2000}
          value={dilemma}
          onChange={(e) => setDilemma(e.target.value)}
          rows={6}
          placeholder="What are you trying to decide? Give the council enough to chew on."
          className="resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {dilemma.length} / 2000
          </span>
          <button
            type="submit"
            disabled={pending || dilemma.trim().length < 10}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "Convening..." : "Convene"}
          </button>
        </div>
      </form>

      {quota && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          You hit your {quota.tier} council limit ({quota.used}/{quota.limit}).
          Resets {new Date(quota.reset_at).toLocaleString()}.{" "}
          {quota.upgrade_url && (
            <a href={quota.upgrade_url} className="underline">Upgrade</a>
          )}
        </div>
      )}

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      {result && <CouncilResult result={result} />}
    </div>
  );
}

function CouncilResult({ result }: { result: CouncilResponse }) {
  return (
    <div className="flex flex-col gap-6">
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {result.replies.map((reply) => (
          <CouncilCard key={reply.slug} reply={reply} />
        ))}
      </section>

      <section className="rounded-md border border-primary/30 bg-primary/5 p-4 shadow-sm">
        <header className="flex items-center justify-between text-sm">
          <h2 className="font-semibold">Judge verdict</h2>
          <span className="font-mono text-muted-foreground">
            confidence {result.verdict.confidence}/10
          </span>
        </header>
        <p className="mt-3 text-sm leading-relaxed">{result.verdict.verdict}</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <VerdictList title="For" items={result.verdict.conditions_for} tone="positive" />
          <VerdictList title="Against" items={result.verdict.conditions_against} tone="negative" />
          <VerdictList title="Missing" items={result.verdict.missing_information} tone="neutral" />
        </div>
      </section>
    </div>
  );
}

function CouncilCard({ reply }: { reply: CouncilReply }) {
  const label = COUNCIL_LABELS[reply.slug] ?? reply.slug;
  if (!reply.text) {
    return (
      <article className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-xs">
        <h3 className="font-semibold">{label}</h3>
        <p className="mt-2 text-muted-foreground">
          {reply.error ?? "No response."}
        </p>
      </article>
    );
  }
  return (
    <article className="rounded-md border border-input bg-background p-3 text-sm shadow-sm">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</h3>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{reply.text}</p>
    </article>
  );
}

function VerdictList({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "positive" | "negative" | "neutral";
}) {
  const dotClass =
    tone === "positive"
      ? "bg-emerald-500"
      : tone === "negative"
      ? "bg-red-500"
      : "bg-muted-foreground";
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {items.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">—</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1.5">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-2 text-xs">
              <span className={`mt-1.5 size-1.5 shrink-0 rounded-full ${dotClass}`} />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
