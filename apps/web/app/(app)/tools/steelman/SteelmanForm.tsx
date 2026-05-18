"use client";

import { useState } from "react";
import Link from "next/link";

interface Counter {
  counter: string;
  response: string;
}

interface SteelmanResponse {
  conversation_id: string;
  assistant_message_id: number | null;
  strongest_version: string;
  assumptions: string[];
  evidence: string[];
  counters: Counter[];
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

export function SteelmanForm() {
  const [position, setPosition] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaExceeded | null>(null);
  const [result, setResult] = useState<SteelmanResponse | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending || position.trim().length < MIN) return;
    setError(null);
    setQuota(null);
    setResult(null);
    setPending(true);
    try {
      const res = await fetch("/api/tools/steelman", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ position }),
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
      setResult((await res.json()) as SteelmanResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label htmlFor="position" className="text-sm font-medium">
          Your position
        </label>
        <textarea
          id="position"
          required
          minLength={MIN}
          maxLength={MAX}
          value={position}
          onChange={(e) => setPosition(e.target.value)}
          rows={8}
          placeholder="The weakest thing you actually believe. Paste it raw — the AI handles the dressing."
          className="resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {position.length} / {MAX}
          </span>
          <button
            type="submit"
            disabled={pending || position.trim().length < MIN}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "Building..." : "Steelman it"}
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

      {result && <SteelmanResult result={result} />}
    </div>
  );
}

function SteelmanResult({ result }: { result: SteelmanResponse }) {
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-md border border-input bg-background p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Strongest version
        </h2>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
          {result.strongest_version}
        </p>
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
        <ListSection title="Assumptions" items={result.assumptions} />
        <ListSection title="Evidence" items={result.evidence} />
      </div>

      <section className="rounded-md border border-input bg-background p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Counters
        </h2>
        <ul className="mt-2 flex flex-col gap-3">
          {result.counters.map((c, i) => (
            <li key={i} className="rounded-md border border-input bg-muted/30 p-3 text-xs">
              <p className="font-medium text-foreground">⚔ {c.counter}</p>
              <p className="mt-1 text-muted-foreground">→ {c.response}</p>
            </li>
          ))}
        </ul>
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

function ListSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="rounded-md border border-input bg-background p-4 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      {items.length === 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">—</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-1.5 text-sm">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-muted-foreground" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
