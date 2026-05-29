"use client";

import Link from "next/link";
import { useActionState } from "react";
import { acceptInvite, type ActionResult } from "./actions";

// Manual invite-code entry. Mirrors the link-click path
// /couples/join/[code] but lets the partner paste the code straight
// onto /couples without ever needing the full URL — handy when the
// link gets mangled in a chat client or only the code travels over
// SMS / phone call. Calls acceptInvite directly so tier caps + RLS
// stay consistent with the clicked-link path.

export function JoinByCodeForm() {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(
    acceptInvite,
    null,
  );
  return (
    <form action={action} className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-start">
      <input
        type="text"
        name="invite_code"
        required
        minLength={8}
        maxLength={64}
        autoComplete="off"
        spellCheck={false}
        placeholder="Paste invite code"
        className="flex-1 rounded-md border border-input bg-background px-3 py-2 font-mono text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Joining…" : "Accept invite"}
      </button>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive sm:basis-full">
          {state.error}
          {state.error.toLowerCase().includes("free tier") && (
            <>
              {" "}
              <Link href="/pricing" className="font-medium underline">
                Upgrade →
              </Link>
            </>
          )}
        </p>
      )}
    </form>
  );
}
