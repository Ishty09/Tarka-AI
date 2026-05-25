"use client";

import { useActionState } from "react";
import { submitPerspective, type ActionResult } from "../actions";

export function PerspectiveForm({ disputeId }: { disputeId: string }) {
  const [state, formAction, pending] = useActionState<ActionResult | null, FormData>(
    submitPerspective,
    null,
  );

  return (
    <form action={formAction} className="mt-3 flex flex-col gap-3">
      <input type="hidden" name="dispute_id" value={disputeId} />
      <textarea
        name="perspective"
        required
        minLength={20}
        maxLength={4000}
        rows={8}
        placeholder="My side: I felt..."
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">
          {state.error}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="inline-flex items-center justify-center self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Submitting…" : "Submit & generate verdict"}
      </button>
    </form>
  );
}
