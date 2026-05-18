"use client";

import { useState } from "react";
import Link from "next/link";

interface AttachmentDynamics {
  user: string;
  partner: string;
  summary: string;
}

interface SuggestedMessage {
  intent: string;
  text: string;
}

interface BreakupResponse {
  conversation_id: string;
  assistant_message_id: number | null;
  attachment_dynamics: AttachmentDynamics;
  reconciliation_likelihood: string;
  reconciliation_reasoning: string;
  missing_things: string[];
  suggested_message: SuggestedMessage;
}

interface QuotaExceeded {
  tier: string;
  limit: number;
  used: number;
  reset_at: string;
  upgrade_url: string | null;
  cost?: number;
}

const THREAD_MIN = 50;
const THREAD_MAX = 5000;

export function BreakupAnalyzerForm() {
  const [thread, setThread] = useState("");
  const [duration, setDuration] = useState("");
  const [userAge, setUserAge] = useState<number | "">("");
  const [partnerAge, setPartnerAge] = useState<number | "">("");
  const [intent, setIntent] = useState<"repair" | "end">("repair");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaExceeded | null>(null);
  const [result, setResult] = useState<BreakupResponse | null>(null);

  function valid(): boolean {
    return (
      thread.trim().length >= THREAD_MIN
      && duration.trim().length > 0
      && typeof userAge === "number"
      && typeof partnerAge === "number"
    );
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending || !valid()) return;
    setError(null);
    setQuota(null);
    setResult(null);
    setPending(true);
    try {
      const res = await fetch("/api/tools/breakup-analyzer", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          text_thread: thread,
          duration,
          user_age: userAge,
          partner_age: partnerAge,
          intent,
        }),
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
      setResult((await res.json()) as BreakupResponse);
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
          <label htmlFor="thread" className="text-sm font-medium">The recent thread</label>
          <textarea
            id="thread"
            required
            minLength={THREAD_MIN}
            maxLength={THREAD_MAX}
            value={thread}
            onChange={(e) => setThread(e.target.value)}
            rows={10}
            placeholder="Paste raw texts — copy/paste from your phone is fine. Speaker labels help but aren't required."
            className="resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">{thread.length} / {THREAD_MAX}</span>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="duration" className="text-sm font-medium">Together how long?</label>
              <input
                id="duration"
                required
                maxLength={80}
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                placeholder="e.g. 2 years"
                className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="user_age" className="text-sm font-medium">Your age</label>
              <input
                id="user_age"
                required
                type="number"
                min={16}
                max={120}
                value={userAge}
                onChange={(e) => setUserAge(e.target.value === "" ? "" : Number(e.target.value))}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="partner_age" className="text-sm font-medium">Their age</label>
              <input
                id="partner_age"
                required
                type="number"
                min={16}
                max={120}
                value={partnerAge}
                onChange={(e) => setPartnerAge(e.target.value === "" ? "" : Number(e.target.value))}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
              />
            </div>
          </div>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">What do you want?</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="flex items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5">
                <input
                  type="radio"
                  name="intent"
                  value="repair"
                  checked={intent === "repair"}
                  onChange={() => setIntent("repair")}
                />
                <span>Try to repair this</span>
              </label>
              <label className="flex items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5">
                <input
                  type="radio"
                  name="intent"
                  value="end"
                  checked={intent === "end"}
                  onChange={() => setIntent("end")}
                />
                <span>End it cleanly</span>
              </label>
            </div>
          </fieldset>

          <button
            type="submit"
            disabled={pending || !valid()}
            className="mt-2 self-end inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "Reading the thread…" : "Analyze"}
          </button>
        </form>
      )}

      {quota && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          You don&apos;t have {quota.cost ?? "enough"} messages left on your {quota.tier} tier
          ({quota.used}/{quota.limit} used). Resets {new Date(quota.reset_at).toLocaleString()}.{" "}
          {quota.upgrade_url && <a href={quota.upgrade_url} className="underline">Upgrade</a>}
        </div>
      )}

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      {result && <BreakupResult result={result} />}
    </div>
  );
}

function BreakupResult({ result }: { result: BreakupResponse }) {
  const dyn = result.attachment_dynamics;
  const tone =
    result.reconciliation_likelihood === "high"
      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700/90"
      : result.reconciliation_likelihood === "medium"
      ? "border-amber-500/40 bg-amber-500/10 text-amber-700/90"
      : "border-red-500/40 bg-red-500/10 text-red-700/90";
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-md border border-input bg-muted/30 p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Attachment dynamics
        </h2>
        <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
          <div><span className="text-muted-foreground">You:</span> <span className="font-medium">{dyn.user}</span></div>
          <div><span className="text-muted-foreground">Partner:</span> <span className="font-medium">{dyn.partner}</span></div>
        </div>
        <p className="mt-2 text-sm leading-relaxed">{dyn.summary}</p>
      </section>

      <section className={`rounded-md border p-4 shadow-sm ${tone}`}>
        <h2 className="text-sm font-semibold uppercase tracking-wide">
          Reconciliation likelihood: {result.reconciliation_likelihood}
        </h2>
        <p className="mt-2 text-sm leading-relaxed">{result.reconciliation_reasoning}</p>
      </section>

      <section className="rounded-md border border-input bg-background p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          What you&apos;re missing
        </h2>
        <ol className="mt-2 flex flex-col gap-2 text-sm">
          {result.missing_things.map((m, i) => (
            <li key={i}>
              <span className="font-medium">{i + 1}.</span> {m}
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-md border border-primary/40 bg-primary/5 p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary/90">
          Suggested message ({result.suggested_message.intent})
        </h2>
        <p className="mt-2 whitespace-pre-wrap font-serif text-base leading-relaxed text-foreground/90">
          {result.suggested_message.text}
        </p>
      </section>

      <div className="text-xs text-muted-foreground">
        Saved to{" "}
        <Link className="underline" href={`/chat/${result.conversation_id}`}>
          a conversation
        </Link>{" "}
        you can keep working in.
      </div>
    </div>
  );
}
