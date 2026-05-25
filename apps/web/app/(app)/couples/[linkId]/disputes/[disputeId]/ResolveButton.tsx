"use client";

import { useActionState } from "react";
import { markDisputeResolved, type ActionResult } from "../actions";

export function ResolveButton({ disputeId }: { disputeId: string }) {
  const [state, formAction, pending] = useActionState<ActionResult | null, FormData>(
    markDisputeResolved,
    null,
  );

  return (
    <form action={formAction} className="flex items-center gap-3">
      <input type="hidden" name="dispute_id" value={disputeId} />
      <button
        type="submit"
        disabled={pending}
        className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
      >
        {pending ? "Saving…" : "Mark resolved"}
      </button>
      {state?.ok === false && (
        <p className="text-xs text-destructive">{state.error}</p>
      )}
    </form>
  );
}
