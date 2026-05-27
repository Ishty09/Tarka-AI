"use client";

import { useActionState, useEffect, useState } from "react";
import Link from "next/link";
import { createInvite, type ActionResult } from "../actions";

interface InvitePayload {
  link_id: string;
  invite_code: string;
}

function getInviteUrl(code: string): string {
  if (typeof window === "undefined") return `/couples/join/${code}`;
  return `${window.location.origin}/couples/join/${code}`;
}

export function InviteForm() {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(
    createInvite,
    null,
  );
  const [copied, setCopied] = useState(false);

  // Reset the "copied" tick when a new invite is created.
  const code = state?.ok && state.payload
    ? (state.payload as InvitePayload).invite_code
    : null;
  useEffect(() => {
    setCopied(false);
  }, [code]);

  if (state?.ok && state.payload) {
    const payload = state.payload as InvitePayload;
    const url = getInviteUrl(payload.invite_code);
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm font-medium">Invite ready. Share this link with your partner.</p>
        <div className="flex items-center gap-2">
          <input
            readOnly
            value={url}
            className="flex-1 rounded-md border border-input bg-muted/30 px-3 py-2 font-mono text-xs"
          />
          <button
            type="button"
            onClick={async () => {
              await navigator.clipboard.writeText(url);
              setCopied(true);
            }}
            className="rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground hover:opacity-90"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          One-shot link · expires in 7 days. If you added their email above,
          we also emailed it directly.
        </p>
        <div className="flex gap-2">
          <Link
            href="/couples"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm hover:bg-accent"
          >
            Back to couples
          </Link>
          <Link
            href={`/couples/${payload.link_id}`}
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Open this link
          </Link>
        </div>
      </div>
    );
  }

  return (
    <form action={action} className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        Ready when you are. By clicking, you&apos;re saying yes to a shared
        chat with one other person; they have to accept on their side.
      </p>
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">
          Partner&apos;s email <span className="text-muted-foreground">(optional)</span>
        </span>
        <span className="text-xs text-muted-foreground">
          Leave blank to share the link yourself over WhatsApp / iMessage / etc.
        </span>
        <input
          type="email"
          name="partner_email"
          maxLength={254}
          autoComplete="email"
          placeholder="them@example.com"
          className="mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">{state.error}</p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Generating…" : "Generate invite link"}
      </button>
    </form>
  );
}
