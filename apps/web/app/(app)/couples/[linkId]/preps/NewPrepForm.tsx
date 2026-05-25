"use client";

import { useActionState } from "react";
import { createPrep, type ActionResult } from "./actions";

export function NewPrepForm({ linkId }: { linkId: string }) {
  const [state, formAction, pending] = useActionState<ActionResult | null, FormData>(
    createPrep,
    null,
  );

  return (
    <form action={formAction} className="mt-3 flex flex-col gap-3">
      <input type="hidden" name="link_id" value={linkId} />
      <input
        type="text"
        name="topic"
        required
        minLength={5}
        maxLength={200}
        placeholder="What's the talk about? — e.g. 'asking to move in together'"
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <input
        type="text"
        name="desired_outcome"
        maxLength={500}
        placeholder="What outcome do you want? (optional)"
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <textarea
        name="context"
        rows={4}
        maxLength={2000}
        placeholder="Optional context — what's been going on, what you're afraid will happen. PRIVATE — partner never sees this."
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">{state.error}</p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="inline-flex w-fit items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Creating…" : "Generate prep"}
      </button>
    </form>
  );
}
