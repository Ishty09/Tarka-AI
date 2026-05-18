"use client";

import { useState } from "react";
import Link from "next/link";
import type { RoastTarget } from "@quarrel/shared/constants";

interface Props {
  target: RoastTarget;
  label: string;
  placeholder: string;
  authed: boolean;
}

interface RoastResponse {
  conversation_id: string;
  assistant_message_id: number | null;
  target: string;
  roast: string;
}

interface QuotaExceeded {
  tier: string;
  limit: number;
  used: number;
  reset_at: string;
  upgrade_url: string | null;
}

const MIN = 20;
const MAX = 6000;

export function RoastInput({ target, label, placeholder, authed }: Props) {
  const [content, setContent] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaExceeded | null>(null);
  const [roast, setRoast] = useState<RoastResponse | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending || content.trim().length < MIN) return;
    setError(null);
    setQuota(null);
    setRoast(null);
    setPending(true);
    try {
      const res = await fetch("/api/tools/roast-my-x", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target, content }),
      });
      if (res.status === 401) {
        // Shouldn't happen — the SSR check renders the signup CTA already.
        window.location.href = `/signup?next=/roast/${target}`;
        return;
      }
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
      setRoast((await res.json()) as RoastResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setPending(false);
    }
  }

  if (!authed) {
    return (
      <div className="flex flex-col gap-3">
        <textarea
          rows={8}
          placeholder={placeholder}
          aria-label={label}
          disabled
          className="resize-none rounded-md border border-input bg-muted/30 px-3 py-2 text-sm shadow-sm opacity-70"
        />
        <p className="text-xs text-muted-foreground">
          Free for the first three roasts. Sign up to roast yours.
        </p>
        <Link
          href={`/signup?next=/roast/${target}`}
          className="self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          Sign up to roast
        </Link>
      </div>
    );
  }

  if (roast) {
    return (
      <div className="flex flex-col gap-4">
        <article className="rounded-md border border-primary/40 bg-primary/5 p-4 shadow-sm">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-primary/90">
            The roast
          </h3>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{roast.roast}</p>
        </article>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            Saved to{" "}
            <Link href={`/chat/${roast.conversation_id}`} className="underline">
              a conversation
            </Link>
            .
          </span>
          <button
            type="button"
            onClick={() => {
              setRoast(null);
              setContent("");
            }}
            className="rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent"
          >
            Roast another
          </button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <label htmlFor="roast_content" className="text-sm font-medium">{label}</label>
      <textarea
        id="roast_content"
        required
        minLength={MIN}
        maxLength={MAX}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={8}
        placeholder={placeholder}
        className="resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {content.length} / {MAX}
        </span>
        <button
          type="submit"
          disabled={pending || content.trim().length < MIN}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Roasting…" : "Roast me"}
        </button>
      </div>

      {quota && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          You hit your {quota.tier} daily message limit ({quota.used}/{quota.limit}).
          Resets {new Date(quota.reset_at).toLocaleString()}.{" "}
          {quota.upgrade_url && <a href={quota.upgrade_url} className="underline">Upgrade</a>}
        </div>
      )}

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </form>
  );
}
