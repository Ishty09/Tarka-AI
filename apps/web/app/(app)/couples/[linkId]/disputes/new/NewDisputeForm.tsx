"use client";

import Link from "next/link";
import { useActionState } from "react";
import { createDispute, type ActionResult } from "../actions";

export function NewDisputeForm({ linkId }: { linkId: string }) {
  const [state, formAction, pending] = useActionState<ActionResult | null, FormData>(
    createDispute,
    null,
  );

  return (
    <form action={formAction} className="mt-6 flex flex-col gap-4">
      <input type="hidden" name="link_id" value={linkId} />
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">Title</span>
        <input
          type="text"
          name="title"
          required
          maxLength={200}
          placeholder="e.g. Sunday night fight about money"
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">Your perspective</span>
        <span className="text-xs text-muted-foreground">
          What happened from your side. Be honest — flattery doesn&apos;t help. 20-4000 characters.
        </span>
        <textarea
          name="perspective"
          required
          minLength={20}
          maxLength={4000}
          rows={10}
          placeholder="On Sunday after dinner I asked about the credit card bill and they..."
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>

      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">
          {state.error}
          {state.upgrade && (
            <>
              {" "}
              <Link href="/pricing" className="font-medium underline">
                Upgrade →
              </Link>
            </>
          )}
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Saving..." : "Submit & notify partner"}
      </button>
    </form>
  );
}
